FROM node:22-slim AS builder

# --max-old-space-size
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV NODE_OPTIONS=--max-old-space-size=8192
ENV TZ=Asia/Shanghai

RUN npm i -g corepack

WORKDIR /app

# copy package.json and pnpm-lock.yaml to workspace
COPY . /app

# The legacy `neverBuiltDependencies` field is not accepted by current pnpm.
# Remove it only inside the build image; the working tree remains untouched.
RUN node -e "const fs=require('fs');const file='package.json';const pkg=JSON.parse(fs.readFileSync(file,'utf8'));delete pkg.pnpm.neverBuiltDependencies;fs.writeFileSync(file,JSON.stringify(pkg,null,2)+'\\n')"

# 安装依赖
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --no-frozen-lockfile
RUN pnpm run build

RUN echo "Builder Success 🎉"

# Export-only target for updating an existing frontend container in place.
FROM scratch AS artifacts
COPY --from=builder /app/plat/dist /

FROM nginx:stable-alpine AS production

# 配置 nginx
RUN echo "types { application/javascript js mjs; }" > /etc/nginx/conf.d/mjs.conf \
    && rm -rf /etc/nginx/conf.d/default.conf

# 复制构建产物
COPY --from=builder /app/plat/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY --from=builder /app/scripts/deploy/nginx.conf /etc/nginx/nginx.conf

EXPOSE 8080

# 启动 nginx
CMD ["nginx", "-g", "daemon off;"]
