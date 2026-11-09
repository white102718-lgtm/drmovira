import type { Plugin } from 'vite';

import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, relative, resolve } from 'node:path';

import { loadEnv, transformWithEsbuild } from 'vite';

import react from '@vitejs/plugin-react';

import { defineConfig } from '@vben/vite-config';

function embeddedReactSourcePlugin(): Plugin {
  return {
    enforce: 'pre',
    name: 'embedded-react-source',
    async transform(code, id) {
      if (!/\/embedded\/(?:adgen-canvas|twitcanva)\/.*\.tsx(?:\?|$)/.test(id)) {
        return null;
      }

      return transformWithEsbuild(code, id, {
        jsx: 'automatic',
        jsxImportSource: 'react',
        loader: 'tsx',
        sourcemap: true,
      });
    },
  };
}

/**
 * Vite's SPA fallback currently handles `/director-desk/` before the copied
 * standalone application can be resolved in this workspace. Mount the built
 * desk explicitly in development so its iframe has the exact same URL as the
 * production `public/` asset.
 */
function directorDeskStaticPlugin(): Plugin {
  const contentTypes: Record<string, string> = {
    '.css': 'text/css; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.ico': 'image/x-icon',
    '.js': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.map': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
  };

  return {
    enforce: 'pre',
    name: 'director-desk-static',
    configureServer(server) {
      const directorDeskRoot = resolve(process.cwd(), 'public/director-desk');

      server.middlewares.use('/director-desk', (request, response, next) => {
        if (request.method && !['GET', 'HEAD'].includes(request.method)) {
          next();
          return;
        }

        let requestPath = 'index.html';
        try {
          const pathname = new URL(
            request.url || '/',
            'http://director-desk.local',
          ).pathname;
          requestPath =
            pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
        } catch {
          next();
          return;
        }

        const filePath = resolve(directorDeskRoot, requestPath);
        if (
          relative(directorDeskRoot, filePath).startsWith('..') ||
          !existsSync(filePath) ||
          statSync(filePath).isDirectory()
        ) {
          next();
          return;
        }

        response.statusCode = 200;
        response.setHeader(
          'Content-Type',
          contentTypes[extname(filePath)] || 'application/octet-stream',
        );
        response.setHeader('Cache-Control', 'no-cache');
        if (request.method === 'HEAD') {
          response.end();
          return;
        }
        createReadStream(filePath).pipe(response);
      });
    },
  };
}

export default defineConfig(async (env) => {
  const mode = env?.mode ?? 'development';
  const envVars = loadEnv(mode, process.cwd(), 'VITE_');
  const backendTarget =
    envVars.VITE_GLOB_BACKEND_PROXY_TARGET || 'http://localhost:8000';
  const rewriteBackendPath =
    envVars.VITE_GLOB_BACKEND_PROXY_REWRITE !== 'false';
  const mainBackendTarget =
    envVars.VITE_GLOB_MAIN_BACKEND_PROXY_TARGET ||
    envVars.VITE_GLOB_MAIN_PROXY_TARGET ||
    'http://localhost:8081';
  const rewriteMainPath =
    envVars.VITE_GLOB_MAIN_BACKEND_PROXY_REWRITE !== 'false';
  const adpulseTarget =
    envVars.VITE_GLOB_ADPULSE_PROXY_TARGET || 'http://localhost:8000';
  const minioTarget =
    envVars.VITE_GLOB_MINIO_URL || 'http://54.179.56.204:9000';
  const agentTarget =
    envVars.VITE_GLOB_AGENT_PROXY_TARGET || 'http://127.0.0.1:8790';
  const adgenTarget =
    envVars.VITE_ADGEN_PROXY_TARGET || 'http://127.0.0.1:7001';
  const rewriteAdgenPath = envVars.VITE_ADGEN_PROXY_REWRITE !== 'false';
  return {
    application: {
      loadingTemplate: 'loading-four-dots.html',
    },
    vite: {
      plugins: [
        directorDeskStaticPlugin(),
        embeddedReactSourcePlugin(),
        react(),
      ],
      resolve: {
        // echarts/zrender 等依赖的 tslib 预构建时会命中 modules/index.js（CJS default
        alias: {
          tslib: 'tslib/tslib.es6.js',
          // Jenkins/CI 偶发解析不到 workspace 软链，直接指向源码入口。
          '@vben-core/shadcn-ui': resolve(
            process.cwd(),
            '../packages/@core/ui-kit/shadcn-ui/src/index.ts',
          ),
        },
      },
      server: {
        host: true,
        port: 5555,
        strictPort: true,
        warmup: {
          // 共享配置会预热 store 等目录，排除测试文件以免开发服务器加载 Vitest。
          clientFiles: ['!./src/**/*.{test,spec}.*', '!./src/**/__tests__/**'],
        },
        proxy: {
          '/main': {
            changeOrigin: true,
            // 本地主业务服务使用 /api/main context-path；测试网关已暴露 /main，不再重写。
            rewrite: rewriteMainPath
              ? (path) => path.replace(/^\/main/, '/api/main')
              : undefined,
            target: mainBackendTarget,
            ws: true,
          },
          '/adgen-api': {
            changeOrigin: true,
            // 本地 AdGen 服务挂在根路径；测试网关已暴露 /adgen-api，必须原样转发。
            rewrite: (path) =>
              rewriteAdgenPath ? path.replace(/^\/adgen-api/, '') : path,
            target: adgenTarget,
            ws: true,
          },
          '/agent': {
            changeOrigin: true,
            // 智能体（adpulse_agent serve 顺带开的 HTTP）路由挂在根上：
            // /agent/v1/chat → /v1/chat。对话走 SSE，不要在这里加压缩或缓冲。
            rewrite: (path) => path.replace(/^\/agent/, ''),
            target: agentTarget,
          },
          '/backend/project': {
            changeOrigin: true,
            // 主业务服务 context-path=/api/main；该规则必须位于通用 /backend 之前。
            // 测试网关已按 /backend/project 转发，开发模式不重写。
            rewrite: rewriteMainPath
              ? (path) => path.replace(/^\/backend/, '/api/main')
              : undefined,
            target: mainBackendTarget,
            ws: true,
          },
          '/backend': {
            changeOrigin: true,
            // 后端 context-path=/api，故将 /backend/* 重写为 /api/*
            // 例：/backend/menus/ → /api/menus/
            rewrite: rewriteBackendPath
              ? (path) => path.replace(/^\/backend/, '/api')
              : undefined,
            target: backendTarget,
            ws: true,
          },
          '/adpulse-api': {
            changeOrigin: true,
            // 广告数据服务无 context-path，路由直接挂在根上：/adpulse-api/dashboard/* → /dashboard/*
            rewrite: (path) => path.replace(/^\/adpulse-api/, ''),
            target: adpulseTarget,
            ws: true,
          },
          '/canvasApi': {
            changeOrigin: true,
            rewrite: (path) => path.replace(/^\/canvasApi/, '/api'),
            target: envVars.VITE_CANVAS_API_TARGET || 'http://localhost:3001',
            ws: true,
          },
          '/library': {
            changeOrigin: true,
            target: envVars.VITE_CANVAS_API_TARGET || 'http://localhost:3001',
          },
          '^/materials/.*\\.[^/?]+': {
            changeOrigin: true,
            target: minioTarget,
          },
          '^/tmp/.*\\.[^/?]+': {
            changeOrigin: true,
            target: minioTarget,
          },
          '/automationApi': {
            changeOrigin: true,
            rewrite: (path) => path.replace(/^\/automationApi/, '/api'),
            target: 'http://47.131.62.227:7015',
            ws: true,
          },
          '/aiReport': {
            changeOrigin: true,
            rewrite: (path) => path.replace(/^\/aiReport/, '/api'),
            target: 'http://18.143.55.165:8000', //正式
            ws: true,
          },
          '/other': {
            changeOrigin: true,
            rewrite: (path) => path.replace(/^\/other/, ''),
            target: 'http://122.248.227.46:5000',
            ws: true,
          },
        },
      },
    },
  };
});
