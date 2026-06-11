const html = (s) => s.join("");

// Three inner interpolations - the exact pattern
const t1 = `${true ? html`
  <button class="btn" disabled=${true === true}
    onClick=${() => {}}>
    ${true ? "Save" : "Update"}
  </button>
` : ''}`;
console.log("t1:", t1);

// Same but without the third interpolation
const t2 = `${true ? html`
  <button class="btn" disabled=${true}
    onClick=${() => {}}>
    Save
  </button>
` : ''}`;
console.log("t2:", t2);

// Same but with two interpolations only
const t3 = `${true ? html`
  <button disabled=${true}>${"x"}</button>
` : ''}`;
console.log("t3:", t3);
