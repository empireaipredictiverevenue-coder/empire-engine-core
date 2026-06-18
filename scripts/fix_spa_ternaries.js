const fs = require("fs");
const acorn = require("acorn");

const file = "empire_command_spa.py";
const code = fs.readFileSync(file, "utf8");

try {
  acorn.parse(code, { ecmaVersion: "latest", sourceType: "module" });
  console.log("No parse errors found with acorn.");
} catch (e) {
  console.log("First parse error at line", e.loc.line, "column", e.loc.column);
  console.log("Message:", e.message);

  const lines = code.split("
");
  const start = Math.max(0, e.loc.line - 3);
  const end = Math.min(lines.length, e.loc.line + 3);
  console.log("
Context:");
  for (let i = start; i < end; i++) {
    const marker = (i === e.loc.line - 1) ? ">>>" : "   ";
    console.log(marker + " " + (i+1) + ": " + lines[i]);
  }
}
