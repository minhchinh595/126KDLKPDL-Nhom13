import { compile } from '@tailwindcss/node';
import { Scanner } from '@tailwindcss/oxide';
import fs from 'fs';
import path from 'path';

async function buildCss() {
  const sourcePath = path.resolve('src/app/globals.source.css');
  const targetPath = path.resolve('src/app/globals.css');

  if (!fs.existsSync(sourcePath)) {
    console.log('globals.source.css not found, skipping compile');
    return;
  }

  const rawCss = fs.readFileSync(sourcePath, 'utf8');
  const compiler = await compile(rawCss, {
    base: path.resolve('src/app'),
    onDependency: () => {},
  });

  const scanner = new Scanner({
    sources: [
      {
        base: process.cwd(),
        pattern: 'src/**/*.{ts,tsx}',
        negated: false,
      },
    ],
  });

  const candidates = scanner.scan();
  const builtCss = compiler.build(candidates);

  fs.writeFileSync(targetPath, builtCss, 'utf8');
  console.log(`[build-css] Compiled ${candidates.length} candidates -> ${builtCss.length} bytes in globals.css`);
}

buildCss().catch((err) => {
  console.error('[build-css] Failed:', err);
  process.exit(1);
});
