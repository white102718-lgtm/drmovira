import type { PluginOption } from 'vite';

import { lazyImport, VxeResolver } from 'vite-plugin-lazy-import';

async function viteVxeTableImportsPlugin(): Promise<PluginOption> {
  return [
    lazyImport({
      // The embedded TwitCanva source is React TSX. Let the React plugin own
      // this narrow subtree instead of parsing it as a Vue/VXE module first.
      exclude: [/embedded\/twitcanva\//],
      resolvers: [
        VxeResolver({
          libraryName: 'vxe-table',
        }),
        VxeResolver({
          libraryName: 'vxe-pc-ui',
        }),
      ],
    }),
  ];
}

export { viteVxeTableImportsPlugin };
