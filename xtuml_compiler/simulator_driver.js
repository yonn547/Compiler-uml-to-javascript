// Driver simulator: menjalankan bundle hasil compile dan menerima perintah
// JSON lewat stdin (satu perintah per baris), membalas satu JSON per baris.

const bundlePath = process.argv[2];
const logs = [];

function formatValue(value) {
  if (typeof value === "string") return value;
  if (value === undefined) return "undefined";
  if (value instanceof Map) return Object.fromEntries(value);
  try {
    return JSON.stringify(value);
  } catch (error) {
    return String(value);
  }
}

function reply(payload) {
  process.stdout.write(JSON.stringify(payload) + "\n");
}

function flushLogs() {
  return logs.splice(0, logs.length);
}

const originalLog = console.log;
console.log = (...args) => {
  logs.push(args.map(formatValue).join(" "));
};

let model;
try {
  model = require(bundlePath);
} catch (error) {
  originalLog(JSON.stringify({ ok: false, error: String(error && error.message || error) }));
  process.exit(0);
}

function getObject(name) {
  const object = model.instances && model.instances[name];
  if (!object) throw new Error(`Instance '${name}' tidak ditemukan`);
  return object;
}

function snapshot() {
  const instances = Object.entries(model.instances || {}).map(([name, object]) => {
    const attributes = {};
    for (const [key, value] of Object.entries(object)) {
      if (key.startsWith("__")) continue;
      attributes[key] =
        value && typeof value === "object" && !(value instanceof Date)
          ? formatValue(value)
          : value;
    }
    return {
      name,
      className: object.className,
      state: object.state,
      attributes,
    };
  });
  return {
    ok: true,
    domain: model.domain,
    instances,
    associations: Object.keys(model.associations || {}),
    logs: flushLogs(),
  };
}

function eventsOf(name) {
  const object = getObject(name);
  const events = new Set();
  for (const machine of object.__stateMachines || []) {
    for (const event of machine.events) events.add(event);
  }
  return Array.from(events);
}

function handle(line) {
  if (!line.trim()) return;
  let command;
  try {
    command = JSON.parse(line);
  } catch (error) {
    reply({ ok: false, error: "Perintah bukan JSON yang valid" });
    return;
  }
  try {
    switch (command.cmd) {
      case "snapshot":
        reply(snapshot());
        break;
      case "events":
        reply({ ok: true, events: eventsOf(command.instance), logs: flushLogs() });
        break;
      case "send": {
        const object = getObject(command.instance);
        const handled = object.generate(command.event, command.payload);
        reply({ ok: true, handled, state: object.state, logs: flushLogs() });
        break;
      }
      case "call": {
        const object = getObject(command.instance);
        if (typeof object[command.method] !== "function") {
          throw new Error(`Method '${command.method}' tidak ditemukan`);
        }
        const result = object[command.method](...(command.args || []));
        reply({ ok: true, result: formatValue(result), logs: flushLogs() });
        break;
      }
      case "reset": {
        const object = getObject(command.instance);
        for (const machine of object.__stateMachines || []) machine.reset(object);
        reply({ ok: true, state: object.state, logs: flushLogs() });
        break;
      }
      case "stop":
        reply({ ok: true });
        process.exit(0);
        break;
      default:
        reply({ ok: false, error: `Perintah '${command.cmd}' tidak dikenal` });
    }
  } catch (error) {
    reply({
      ok: false,
      error: String((error && error.message) || error),
      logs: flushLogs(),
    });
  }
}

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  const lines = buffer.split("\n");
  buffer = lines.pop();
  for (const line of lines) handle(line);
});
process.stdin.on("end", () => {
  if (buffer.trim()) handle(buffer);
});
