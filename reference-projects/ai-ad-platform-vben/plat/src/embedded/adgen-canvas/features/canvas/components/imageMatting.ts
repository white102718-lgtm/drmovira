/**
 * 智能抠图：把主体提示交给模型，结果直接用模型返回的图。
 * 不再做收边、去光晕、洪水填充等后处理，避免把轮廓做糙。
 * 画笔只改模型图自己的透明通道；最终仍编码为带 alpha 的 PNG。
 */

export const SMART_MATTING_MODEL = 'gpt-image-2';

export const SMART_MATTING_PROMPT = [
  'The second image is a user hint mask aligned to the first photo.',
  'White marks the subject to keep; black is ignored.',
  'Return a cutout of that subject: same framing, subject in color, background fully transparent.',
  'Do not add outline, stroke, glow, halo, or shadow.',
  'Do not return a black-and-white mask or a photo on a white backdrop.',
].join(' ');

export interface MattingPoint {
  x: number;
  y: number;
}

export interface MattingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

const channel = (data: Uint8ClampedArray, index: number) => data[index] ?? 0;

export const normalizeBox = (start: MattingPoint, end: MattingPoint): MattingBox => {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  return {
    x: clamp01(x),
    y: clamp01(y),
    width: clamp01(Math.max(start.x, end.x) - x),
    height: clamp01(Math.max(start.y, end.y) - y),
  };
};

export const hasMattingSelection = (points: MattingPoint[], box?: MattingBox | null) => (
  points.length > 0 || Boolean(box && box.width > 0.02 && box.height > 0.02)
);

export const loadImageElement = async (url: string) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`无法读取图片（HTTP ${response.status}）`);
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const element = new Image();
    element.onload = () => resolve(element);
    element.onerror = () => reject(new Error('图片加载失败'));
    element.src = objectUrl;
  });
  return { image, revoke: () => URL.revokeObjectURL(objectUrl) };
};

export const createHintMaskDataUrl = (
  width: number,
  height: number,
  points: MattingPoint[],
  box?: MattingBox | null,
) => {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width));
  canvas.height = Math.max(1, Math.round(height));
  const context = canvas.getContext('2d');
  if (!context) throw new Error('无法创建主体提示蒙版');
  context.fillStyle = '#000000';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#ffffff';
  if (box && box.width > 0 && box.height > 0) {
    context.fillRect(
      box.x * canvas.width,
      box.y * canvas.height,
      box.width * canvas.width,
      box.height * canvas.height,
    );
  }
  const radius = Math.max(18, Math.min(canvas.width, canvas.height) * 0.045);
  for (const point of points) {
    context.beginPath();
    context.arc(point.x * canvas.width, point.y * canvas.height, radius, 0, Math.PI * 2);
    context.fill();
  }
  return canvas.toDataURL('image/png');
};

const readImageData = (image: HTMLImageElement) => {
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth || image.width;
  canvas.height = image.naturalHeight || image.height;
  const context = canvas.getContext('2d', { willReadFrequently: true, alpha: true });
  if (!context) throw new Error('无法读取抠图结果');
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return context.getImageData(0, 0, canvas.width, canvas.height);
};

const writeGray = (target: ImageData, index: number, value: number) => {
  const next = Math.max(0, Math.min(255, Math.round(value)));
  target.data[index] = next;
  target.data[index + 1] = next;
  target.data[index + 2] = next;
  target.data[index + 3] = 255;
};

/** 只有接近纯黑白、且几乎没有中间灰的图才当成遮罩，避免把彩色抠图当成灰度透明度。 */
export const isGrayscaleMatte = (imageData: ImageData) => {
  const { data } = imageData;
  let samples = 0;
  let chromaSum = 0;
  let extreme = 0;
  for (let index = 0; index < data.length; index += 16) {
    const red = channel(data, index);
    const green = channel(data, index + 1);
    const blue = channel(data, index + 2);
    chromaSum += Math.max(red, green, blue) - Math.min(red, green, blue);
    const luma = red * 0.299 + green * 0.587 + blue * 0.114;
    if (luma < 24 || luma > 232) extreme += 1;
    samples += 1;
  }
  return samples > 0 && chromaSum / samples < 12 && extreme / samples > 0.72;
};

const hasUsefulAlpha = (imageData: ImageData) => {
  let transparent = 0;
  const total = imageData.width * imageData.height;
  for (let index = 0; index < imageData.data.length; index += 16) {
    if (channel(imageData.data, index + 3) < 250) transparent += 1;
  }
  const sampled = Math.max(1, Math.ceil(total / 4));
  return transparent / sampled > 0.02;
};

/** 粘贴/导入时判断是不是带透明通道的 PNG，用来决定节点要不要铺棋盘格。 */
export const imageBlobHasTransparency = async (blob: Blob) => {
  if (!blob.type.startsWith('image/') || /jpe?g$/i.test(blob.type)) return false;
  const objectUrl = URL.createObjectURL(blob);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error('图片加载失败'));
      element.src = objectUrl;
    });
    return hasUsefulAlpha(readImageData(image));
  } catch {
    return false;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
};

const isNearWhite = (red: number, green: number, blue: number) => (
  red > 242 && green > 242 && blue > 242
);

const matteBackdropRatio = (matte: ImageData) => {
  let transparent = 0;
  const total = matte.width * matte.height;
  for (let index = 0; index < matte.data.length; index += 4) {
    if (channel(matte.data, index) < 16) transparent += 1;
  }
  return total > 0 ? transparent / total : 0;
};

const cornersLookTransparent = (imageData: ImageData) => {
  const { width, height, data } = imageData;
  const insetX = Math.max(1, Math.round(width * 0.02));
  const insetY = Math.max(1, Math.round(height * 0.02));
  const samples = [
    [0, 0],
    [width - 1, 0],
    [0, height - 1],
    [width - 1, height - 1],
    [insetX, insetY],
    [width - 1 - insetX, insetY],
    [insetX, height - 1 - insetY],
    [width - 1 - insetX, height - 1 - insetY],
  ];
  let transparent = 0;
  for (const [x, y] of samples) {
    if (channel(data, (y * width + x) * 4 + 3) < 32) transparent += 1;
  }
  return transparent >= 3;
};

/** 只清掉连通到画面边缘的近白底，避免把衣服高光抠成洞。 */
const createEdgeFloodMatte = (imageData: ImageData) => {
  const { width, height, data } = imageData;
  const visited = new Uint8Array(width * height);
  const stack: number[] = [];
  const isBackdrop = (pixel: number) => {
    const index = pixel * 4;
    const alpha = channel(data, index + 3);
    if (alpha < 16) return true;
    return isNearWhite(channel(data, index), channel(data, index + 1), channel(data, index + 2));
  };
  const enqueue = (x: number, y: number) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const pixel = y * width + x;
    if (visited[pixel] || !isBackdrop(pixel)) return;
    visited[pixel] = 1;
    stack.push(pixel);
  };
  for (let x = 0; x < width; x += 1) {
    enqueue(x, 0);
    enqueue(x, height - 1);
  }
  for (let y = 0; y < height; y += 1) {
    enqueue(0, y);
    enqueue(width - 1, y);
  }
  while (stack.length > 0) {
    const pixel = stack.pop();
    if (pixel === undefined) break;
    const x = pixel % width;
    const y = (pixel / width) | 0;
    enqueue(x - 1, y);
    enqueue(x + 1, y);
    enqueue(x, y - 1);
    enqueue(x, y + 1);
  }
  const next = new ImageData(width, height);
  for (let pixel = 0; pixel < visited.length; pixel += 1) {
    writeGray(next, pixel * 4, visited[pixel] ? 0 : 255);
  }
  return next;
};

/**
 * 只从模型图里取透明通道，不做形态学收边。
 * 有真实透明底就用 alpha；黑白遮罩用亮度；否则只清掉连到边缘的白底。
 */
export const extractMatteData = (modelImage: HTMLImageElement) => {
  const imageData = readImageData(modelImage);
  const next = new ImageData(imageData.width, imageData.height);
  const useAlpha = hasUsefulAlpha(imageData) && cornersLookTransparent(imageData);
  const useGray = !useAlpha && isGrayscaleMatte(imageData);
  if (!useAlpha && !useGray) {
    return createEdgeFloodMatte(imageData);
  }
  for (let index = 0; index < imageData.data.length; index += 4) {
    const red = channel(imageData.data, index);
    const green = channel(imageData.data, index + 1);
    const blue = channel(imageData.data, index + 2);
    const alpha = channel(imageData.data, index + 3);
    const value = useGray
      ? Math.round(red * 0.299 + green * 0.587 + blue * 0.114)
      : alpha;
    writeGray(next, index, value);
  }
  if (matteBackdropRatio(next) >= 0.02) return next;
  return createEdgeFloodMatte(imageData);
};

const sampleMatteNearest = (matte: ImageData, x: number, y: number) => {
  const sourceX = Math.min(matte.width - 1, Math.max(0, Math.round(x)));
  const sourceY = Math.min(matte.height - 1, Math.max(0, Math.round(y)));
  return channel(matte.data, (sourceY * matte.width + sourceX) * 4);
};

/** 用模型图像素 + 模型透明通道合成，不再改颜色。 */
const buildCutoutImageData = (
  source: HTMLImageElement,
  matte: ImageData,
) => {
  const width = source.naturalWidth || source.width;
  const height = source.naturalHeight || source.height;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true, alpha: true });
  if (!context) throw new Error('无法读取抠图结果');
  context.clearRect(0, 0, width, height);
  context.drawImage(source, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height);
  const scaleX = matte.width / width;
  const scaleY = matte.height / height;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const sourceAlpha = channel(pixels.data, index + 3);
      // 先还原预乘，再只替换 alpha，避免人像被叠成半透明。
      if (sourceAlpha > 0 && sourceAlpha < 255) {
        const coverage = sourceAlpha / 255;
        pixels.data[index] = Math.min(255, channel(pixels.data, index) / coverage);
        pixels.data[index + 1] = Math.min(255, channel(pixels.data, index + 1) / coverage);
        pixels.data[index + 2] = Math.min(255, channel(pixels.data, index + 2) / coverage);
      }
      pixels.data[index + 3] = sampleMatteNearest(matte, x * scaleX, y * scaleY);
    }
  }
  return pixels;
};

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a] as const;

/** 上传对象名必须每次不同，否则会覆盖同名文件，节点继续显示上一次抠图。 */
export const createSmartMattingFilename = () => {
  const suffix = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `canvas-smart-matting-${suffix}.png`;
};

const encodeRgbaPngFile = async (imageData: ImageData, filename: string) => {
  const canvas = document.createElement('canvas');
  canvas.width = imageData.width;
  canvas.height = imageData.height;
  const context = canvas.getContext('2d', { alpha: true });
  if (!context) throw new Error('无法编码透明 PNG');
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.putImageData(imageData, 0, 0);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((next) => (next ? resolve(next) : reject(new Error('抠图结果为空'))), 'image/png');
  });
  const header = new Uint8Array(await blob.slice(0, 8).arrayBuffer());
  const isPng = PNG_SIGNATURE.every((byte, index) => header[index] === byte);
  if (!isPng) throw new Error('抠图结果未能导出为带透明通道的 PNG');
  const stem = filename.replace(/\.[^.]+$/i, '') || 'canvas-smart-matting';
  return new File([blob], `${stem}.png`, { type: 'image/png' });
};

const readCutoutImageDataWithWebgl = (
  source: HTMLImageElement,
  matte: ImageData,
) => {
  const width = source.naturalWidth || source.width;
  const height = source.naturalHeight || source.height;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const gl = canvas.getContext('webgl2', {
    premultipliedAlpha: false,
    preserveDrawingBuffer: true,
    alpha: true,
  }) || canvas.getContext('webgl', {
    premultipliedAlpha: false,
    preserveDrawingBuffer: true,
    alpha: true,
  });
  if (!gl) return null;

  const vertexSource = `
    attribute vec2 a_position;
    varying vec2 v_uv;
    void main() {
      v_uv = a_position * 0.5 + 0.5;
      gl_Position = vec4(a_position, 0.0, 1.0);
    }
  `;
  const fragmentSource = `
    precision mediump float;
    varying vec2 v_uv;
    uniform sampler2D u_image;
    uniform sampler2D u_matte;
    void main() {
      vec2 uv = vec2(v_uv.x, 1.0 - v_uv.y);
      vec4 color = texture2D(u_image, uv);
      float alpha = texture2D(u_matte, uv).r;
      gl_FragColor = vec4(color.rgb, alpha);
    }
  `;

  const compile = (type: number, shaderSource: string) => {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, shaderSource);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  };

  const vertexShader = compile(gl.VERTEX_SHADER, vertexSource);
  const fragmentShader = compile(gl.FRAGMENT_SHADER, fragmentSource);
  if (!vertexShader || !fragmentShader) return null;
  const program = gl.createProgram();
  if (!program) return null;
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  gl.useProgram(program);

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
    -1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1,
  ]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, 'a_position');
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  const uploadTexture = (unit: number, image: HTMLImageElement | HTMLCanvasElement, uniform: string) => {
    const texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, 0);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, 0);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
    gl.uniform1i(gl.getUniformLocation(program, uniform), unit);
  };

  const matteCanvas = document.createElement('canvas');
  matteCanvas.width = matte.width;
  matteCanvas.height = matte.height;
  const matteContext = matteCanvas.getContext('2d');
  if (!matteContext) return null;
  matteContext.putImageData(matte, 0, 0);

  uploadTexture(0, source, 'u_image');
  uploadTexture(1, matteCanvas, 'u_matte');
  gl.disable(gl.BLEND);
  gl.viewport(0, 0, width, height);
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT);
  gl.drawArrays(gl.TRIANGLES, 0, 6);

  const raw = new Uint8Array(width * height * 4);
  gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, raw);
  const imageData = new ImageData(new Uint8ClampedArray(width * height * 4), width, height);
  for (let y = 0; y < height; y += 1) {
    const dest = y * width * 4;
    const src = (height - 1 - y) * width * 4;
    imageData.data.set(raw.subarray(src, src + width * 4), dest);
  }
  return imageData;
};

export const drawCutoutPreview = (
  target: HTMLCanvasElement,
  source: HTMLImageElement,
  matte?: ImageData | null,
) => {
  const context = target.getContext('2d', { alpha: true });
  if (!context) return;
  context.clearRect(0, 0, target.width, target.height);
  if (!matte) {
    context.drawImage(source, 0, 0, target.width, target.height);
    return;
  }
  const cutout = buildCutoutImageData(source, matte);
  const preview = document.createElement('canvas');
  preview.width = cutout.width;
  preview.height = cutout.height;
  const previewContext = preview.getContext('2d', { alpha: true });
  if (!previewContext) return;
  previewContext.putImageData(cutout, 0, 0);
  context.drawImage(preview, 0, 0, target.width, target.height);
};

export const compositeCutoutFile = async (
  source: HTMLImageElement,
  matte: ImageData,
  filename = createSmartMattingFilename(),
) => {
  const imageData = readCutoutImageDataWithWebgl(source, matte) || buildCutoutImageData(source, matte);
  return encodeRgbaPngFile(imageData, filename);
};

export const paintMatteStroke = (
  matte: ImageData,
  from: MattingPoint,
  to: MattingPoint,
  radiusRatio: number,
  mode: 'erase' | 'restore',
  restoreSource?: ImageData,
) => {
  const radius = Math.max(6, Math.min(matte.width, matte.height) * radiusRatio);
  const steps = Math.max(1, Math.hypot(
    (to.x - from.x) * matte.width,
    (to.y - from.y) * matte.height,
  ) / Math.max(1, radius * 0.45));
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    const centerX = Math.round((from.x + (to.x - from.x) * t) * (matte.width - 1));
    const centerY = Math.round((from.y + (to.y - from.y) * t) * (matte.height - 1));
    const minX = Math.max(0, centerX - Math.ceil(radius));
    const maxX = Math.min(matte.width - 1, centerX + Math.ceil(radius));
    const minY = Math.max(0, centerY - Math.ceil(radius));
    const maxY = Math.min(matte.height - 1, centerY + Math.ceil(radius));
    for (let y = minY; y <= maxY; y += 1) {
      for (let x = minX; x <= maxX; x += 1) {
        const distance = Math.hypot(x - centerX, y - centerY);
        if (distance > radius) continue;
        const falloff = 1 - distance / radius;
        const index = (y * matte.width + x) * 4;
        const current = channel(matte.data, index);
        const restore = restoreSource ? channel(restoreSource.data, index) : 255;
        const next = mode === 'erase'
          ? current * (1 - falloff)
          : current + (restore - current) * falloff;
        matte.data[index] = next;
        matte.data[index + 1] = next;
        matte.data[index + 2] = next;
      }
    }
  }
  return matte;
};
