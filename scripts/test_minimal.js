const html = (s) => s.join("");

const noteInputs = {}, l = {id:1}, busy = null;

// Test with the same condition structure
const t1 = `${noteInputs[l.id] !== undefined && noteInputs[l.id].trim() !== (l.notes || '').trim() ? html`
  <button>test</button>
` : ''}`;
console.log("t1:", t1);

// Simpler condition
const t2 = `${true && true ? html`
  <button>test</button>
` : ''}`;
console.log("t2:", t2);

// Even simpler - just a single function call
const t3 = `${true ? html`
  <button>test</button>
` : ''}`;
console.log("t3:", t3);
