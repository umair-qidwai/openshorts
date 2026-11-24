import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

// Execute the modal's real selection handlers with synchronous state setters.
// JSX needs no runtime here: these handlers only transition caption state.
const source = readFileSync(new URL('./SubtitleModal.jsx', import.meta.url), 'utf8');
const animationMap = source.match(/const ANIMATION_TO_EFFECT = (.*);/)[1];
const reverseMap = source.match(/const EFFECT_TO_ANIMATION = (.*);/)[1];
const presets = source.slice(source.indexOf('const CAPTION_PRESETS = '), source.indexOf('// Mirrors subtitles._luminance'));
const handlers = source.slice(source.indexOf('    const setAnimation = '), source.indexOf('    const maxChars = '));
function selectAfterClassic(animation) {
    const state = {};
    const setters = {};
    for (const key of ['activePreset', 'style', 'effect', 'highlightColor', 'baseOpacity',
        'uppercase', 'fontName', 'borderWidth', 'fontColor', 'bgOpacity', 'reveal',
        'shadow', 'oneWord', 'fontSize', 'animationState']) {
        setters[`set${key[0].toUpperCase()}${key.slice(1)}`] = value => { state[key] = value; };
    }
    const context = { ...setters, state, selection: animation };
    runInNewContext(`
        const ANIMATION_TO_EFFECT = ${animationMap};
        const EFFECT_TO_ANIMATION = ${reverseMap};
        ${presets}
        ${handlers}
        applyPreset(CAPTION_PRESETS.find(p => p.id === 'classic'));
        const style = state.style;
        setAnimation(selection);
    `, context);
    return state;
}

test('Classic then Rounded explicitly enters native karaoke rounded mode', () => {
    const state = selectAfterClassic('rounded');
    assert.equal(state.animationState, 'rounded');
    assert.equal(state.style, 'karaoke');
    assert.equal(state.effect, 'rounded'); // activates native preview/apply guard
    assert.equal(state.fontName, 'Barlow Condensed Black');
    assert.equal(state.baseOpacity, 1);
    assert.equal(state.bgOpacity, 0);
});

test('Classic then a legacy animation preserves legacy Classic behavior', () => {
    for (const animation of ['none', 'pop', 'word-highlight', 'karaoke']) {
        const state = selectAfterClassic(animation);
        assert.equal(state.style, 'classic');
        assert.equal(state.effect, 'none');
        assert.equal(state.animationState, animation);
    }
});
