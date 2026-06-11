const html = (s) => s.join("");

// Test: backtick and } on the same line
const t1 = `${true ? html`test` : ''}`;
console.log("T1 same line:", t1);

// Test: backtick and } on different lines  
const t2 = `${true ? html`
test
` : ''}`;
console.log("T2 different lines:", t2);

// Test: multi-line with ${} interpolation inside
const busyname = false;
const t3 = `${true ? html`
  ${busyname ? 'yes' : 'no'}
` : ''}`;
console.log("T3 with inner:", t3);

// Test: more complex inner interpolation
const t4 = `${true ? html`
  <div>${true ? 'a' : 'b'}</div>
` : ''}`;
console.log("T4 complex:", t4);
