import { defineConfig } from '@playwright/test';
import path from 'node:path';

// The app under test reads a catalogue groomed from groom's synthetic fixture library
// (scripts/fixture-catalogue.mjs), never the real loop library or SoundFonts.
const fixtures = path.resolve(import.meta.dirname, '.fixtures');

export default defineConfig({
	webServer: {
		command: 'node scripts/fixture-catalogue.mjs && npm run build && npm run preview',
		port: 4173,
		env: {
			DRUM_DATA_DIR: path.join(fixtures, 'data'),
			DRUM_LIBRARY_DIR: path.join(fixtures, 'library'),
			DRUM_SOUNDFONT_DIR: path.join(fixtures, 'no-soundfonts'),
			DRUM_EXPORT_DIR: path.join(fixtures, 'exports')
		}
	},
	testMatch: '**/*.e2e.{ts,js}'
});
