// Test 1: Simple nested template (no tagged template)
const t1 = `${true ? `test` : ''}`;
console.log("T1 pass");

// Test 2: Tagged template with interpolation
const t2 = `${true ? String.raw`test` : ''}`;
console.log("T2 pass");

// Test 3: The exact pattern from the bug
const t3 = `${true ? html`inner ${true ? "x" : "y"}` : ''}`;
console.log("T3 pass");

// Test 4: Multi-line version
const t4 = `${true ? html`
  <div>${true ? "x" : "y"}</div>
` : ''}`;
console.log("T4 pass");
