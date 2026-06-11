const html = (s) => s.join("");

// Level 1: Simple single template
const a = html`hello ${'world'}`;
console.log("a pass");

// Level 2: Template inside interpolation of another template
const b = `${true ? html`hello` : ''}`;
console.log("b pass");

// Level 3: Template inside interpolation, with inner interpolation
const c = `${true ? html`hello ${'world'}` : ''}`;
console.log("c pass");

// Level 4: Template inside interpolation, template inside interpolation
const d = `${true ? html`${true ? 'a' : 'b'}` : ''}`;
console.log("d pass");

// Level 4b: Multi-line version
const e = `${true ? html`
  ${true ? 'a' : 'b'}
` : ''}`;
console.log("e pass");

// Level 4c: with arrow function
const f = `${true ? html`
  <button onClick=${() => {}}>${'x'}</button>
` : ''}`;
console.log("f pass");
