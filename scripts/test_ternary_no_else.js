const html = (s) => s.join("");

// Test 1: Ternary without else - is this valid?
const t1 = `${true ? "yes"}`;
console.log("t1:", t1);

// Test 2: Ternary without else in tagged template
const t2 = `${true ? html`<div>test</div>`}`;
console.log("t2:", t2);

// Test 3: With else (should work)
const t3 = `${true ? html`<div>test</div>` : ''}`;
console.log("t3:", t3);

// Test 4: Without else, multi-line, with inner interpolation
const t4 = `${true ? html`
  <button disabled=${true}>${"x"}</button>
`}`;
console.log("t4:", t4);
