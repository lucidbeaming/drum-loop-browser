// General MIDI drum map (notes 27-87), with short names for the drum grid.
const GM_DRUMS: Record<number, string> = {
	27: 'High Q',
	28: 'Slap',
	29: 'Scratch Push',
	30: 'Scratch Pull',
	31: 'Sticks',
	32: 'Square Click',
	33: 'Metronome Click',
	34: 'Metronome Bell',
	35: 'Acoustic Kick',
	36: 'Kick',
	37: 'Side Stick',
	38: 'Snare',
	39: 'Clap',
	40: 'Electric Snare',
	41: 'Low Floor Tom',
	42: 'Closed Hat',
	43: 'High Floor Tom',
	44: 'Pedal Hat',
	45: 'Low Tom',
	46: 'Open Hat',
	47: 'Low-Mid Tom',
	48: 'Hi-Mid Tom',
	49: 'Crash',
	50: 'High Tom',
	51: 'Ride',
	52: 'China',
	53: 'Ride Bell',
	54: 'Tambourine',
	55: 'Splash',
	56: 'Cowbell',
	57: 'Crash 2',
	58: 'Vibraslap',
	59: 'Ride 2',
	60: 'Hi Bongo',
	61: 'Low Bongo',
	62: 'Mute Hi Conga',
	63: 'Open Hi Conga',
	64: 'Low Conga',
	65: 'High Timbale',
	66: 'Low Timbale',
	67: 'High Agogo',
	68: 'Low Agogo',
	69: 'Cabasa',
	70: 'Maracas',
	71: 'Short Whistle',
	72: 'Long Whistle',
	73: 'Short Guiro',
	74: 'Long Guiro',
	75: 'Claves',
	76: 'Hi Wood Block',
	77: 'Low Wood Block',
	78: 'Mute Cuica',
	79: 'Open Cuica',
	80: 'Mute Triangle',
	81: 'Open Triangle',
	82: 'Shaker',
	83: 'Jingle Bell',
	84: 'Belltree',
	85: 'Castanets',
	86: 'Mute Surdo',
	87: 'Open Surdo'
};

// Grid rows top to bottom, like a DAW drum editor: cymbals, hats, toms high to low, snares, kicks.
// Notes not listed here (percussion) go between the cymbals and the hats, in note order.
const ROW_ORDER = [
	49, 57, 55, 52, 51, 59, 53, 46, 44, 42, 50, 48, 47, 45, 43, 41, 39, 37, 40, 38, 36, 35
];
const PERCUSSION_SLOT = ROW_ORDER.indexOf(46);

export function drumName(key: number): string {
	return GM_DRUMS[key] ?? `Note ${key}`;
}

/** The distinct notes in a loop, in grid-row order. */
export function gridRows(keys: Iterable<number>): number[] {
	const rank = (k: number) => {
		const i = ROW_ORDER.indexOf(k);
		return i >= 0 ? i : PERCUSSION_SLOT - 0.5 + k / 1000;
	};
	return [...new Set(keys)].sort((a, b) => rank(a) - rank(b));
}
