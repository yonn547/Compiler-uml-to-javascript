// Runtime kecil untuk kode JavaScript hasil compile xtUML.
// File ini dipakai dua kali: disalin sebagai src/runtime.js (project mode)
// dan disisipkan ke bundle satu file (dengan baris `export ` dibuang).

export function parseMultiplicity(value) {
  const text = String(value == null ? "1" : value).trim() || "1";
  if (text === "*") return { min: 0, max: Infinity, many: true };
  if (text.includes("..")) {
    const [low, high] = text.split("..");
    const min = low === "*" ? 0 : Number(low);
    const max = high === "*" ? Infinity : Number(high);
    return { min, max, many: max !== 1 };
  }
  const count = Number(text);
  return { min: count, max: count, many: count > 1 };
}

export class ObjectRegistry {
  constructor() {
    this.items = [];
  }

  add(object) {
    if (!this.items.includes(object)) this.items.push(object);
    return object;
  }

  remove(object) {
    const index = this.items.indexOf(object);
    if (index >= 0) {
      this.items.splice(index, 1);
      return true;
    }
    return false;
  }

  all(className) {
    if (!className) return this.items.slice();
    return this.items.filter((object) => object._class === className);
  }

  find(className, predicate) {
    return this.all(className).find(predicate);
  }
}

export class UmlObject {
  constructor(attributes = {}) {
    Object.assign(this, attributes);
    if (!this._class) this._class = this.constructor.name;
    this.__states = new Map();
    this.__stateMachines = (this.constructor.__stateMachines || []).slice();
    UmlObject.registry.add(this);
  }

  get className() {
    return this._class;
  }

  get state() {
    const machine = this.__stateMachines[0];
    return machine ? machine.stateOf(this) : null;
  }

  stateOf(machineName) {
    const machine = this.__stateMachines.find((item) => item.name === machineName);
    return machine ? machine.stateOf(this) : null;
  }

  generate(event, payload) {
    let handled = false;
    for (const machine of this.__stateMachines) {
      if (machine.dispatch(this, event, payload)) handled = true;
    }
    return handled;
  }

  toJSON() {
    const result = { _class: this._class };
    for (const [key, value] of Object.entries(this)) {
      if (!key.startsWith("__")) result[key] = value;
    }
    return result;
  }
}

export class Association {
  constructor(name, endA, endB) {
    this.name = name;
    this.ends = [this._normalize(endA), this._normalize(endB)];
    this.links = [];
    this.classes = null;
  }

  _normalize(end) {
    const parsed = parseMultiplicity(end.multiplicity);
    return {
      className: end.className || end.class_name || "Object",
      role: end.role || "objects",
      multiplicity: end.multiplicity || "1",
      min: parsed.min,
      max: parsed.max,
      many: parsed.many,
    };
  }

  install(ClassA, ClassB) {
    this.classes = [ClassA, ClassB];
    for (const Class of [ClassA, ClassB]) {
      if (!Array.isArray(Class.__associations)) Class.__associations = [];
      if (!Class.__associations.includes(this)) Class.__associations.push(this);
    }
    this._defineNavigation(ClassA.prototype, this.ends[0], 0);
    this._defineNavigation(ClassB.prototype, this.ends[1], 1);
    return this;
  }

  _defineNavigation(prototype, end, side) {
    if (Object.prototype.hasOwnProperty.call(prototype, end.role)) return;
    Object.defineProperty(prototype, end.role, {
      configurable: true,
      enumerable: false,
      get() {
        return this.__associationNavigate(end, side);
      },
    });
  }

  link(a, b) {
    if (!a || !b) throw new Error(`[${this.name}] link memerlukan dua instance`);
    if (this.classes) {
      if (!(a instanceof this.classes[0]) || !(b instanceof this.classes[1])) {
        throw new Error(`[${this.name}] tipe instance tidak sesuai dengan ujung association`);
      }
    }
    if (this.isLinked(a, b)) return false;
    this._checkMax(0, a);
    this._checkMax(1, b);
    this.links.push({ a, b });
    return true;
  }

  unlink(a, b) {
    const before = this.links.length;
    this.links = this.links.filter(
      (item) => !(item.a === a && (b === undefined || item.b === b)),
    );
    return this.links.length !== before;
  }

  isLinked(a, b) {
    return this.links.some((item) => item.a === a && item.b === b);
  }

  navigate(object, side) {
    if (!object) return this.ends[side].many ? [] : null;
    const result = [];
    for (const item of this.links) {
      if (side === 0 && item.a === object) result.push(item.b);
      if (side === 1 && item.b === object) result.push(item.a);
    }
    return this.ends[side].many ? result : result[0] || null;
  }

  linkedCount(object, side) {
    return this.links.filter((item) =>
      side === 0 ? item.a === object : item.b === object,
    ).length;
  }

  _checkMax(side, object) {
    const maximum = this.ends[side].max;
    if (this.linkedCount(object, side) >= maximum) {
      throw new Error(
        `[${this.name}] role '${this.ends[side].role}' hanya mengizinkan ` +
          `${maximum === Infinity ? "∞" : maximum} link`,
      );
    }
  }
}

// Dipanggil oleh getter yang dipasang Association.install.
Object.defineProperty(UmlObject.prototype, "__associationNavigate", {
  enumerable: false,
  configurable: true,
  value: function __associationNavigate(end, side) {
    const association = this.constructor.__associations || [];
    const found = association.find((item) => item.ends[side] === end);
    return found ? found.navigate(this, side) : null;
  },
});

export class StateMachine {
  constructor({ name, owner, initial, states = {}, events = [], transitions = [] }) {
    this.name = name || "stateMachine";
    this.owner = owner || "Object";
    this.initial = initial || Object.keys(states)[0] || "";
    this.states = states;
    this.events = events;
    this.transitions = transitions;
    this.debug = false;
  }

  install(Class) {
    if (!Array.isArray(Class.__stateMachines)) Class.__stateMachines = [];
    if (!Class.__stateMachines.includes(this)) Class.__stateMachines.push(this);
    if (!Array.isArray(Class.__associations)) Class.__associations = [];
    if (!Object.prototype.hasOwnProperty.call(Class.prototype, "state")) {
      Object.defineProperty(Class.prototype, "state", {
        configurable: true,
        get() {
          return this.__stateMachines.length ? this.__stateMachines[0].stateOf(this) : null;
        },
      });
    }
    return this;
  }

  stateOf(object) {
    return object.__states.get(this.name) || this.initial;
  }

  can(object, event, payload) {
    const current = this.stateOf(object);
    return this.transitions.some(
      (transition) =>
        transition.from === current &&
        transition.event === event &&
        (!transition.guard || transition.guard.call(object, payload)),
    );
  }

  dispatch(object, event, payload) {
    if (event != null && !this.events.includes(event)) return false;
    const current = this.stateOf(object);
    const candidates = this.transitions.filter(
      (transition) => transition.from === current && transition.event === event,
    );
    const transition = candidates.find(
      (item) => !item.guard || !!item.guard.call(object, payload),
    );
    if (!transition) return false;

    const fromState = this.states[current] || {};
    const toState = this.states[transition.to] || {};
    if (fromState.exit) fromState.exit.call(object, payload, event);
    object.__states.set(this.name, transition.to);
    if (toState.entry) toState.entry.call(object, payload, event);
    if (transition.action) transition.action.call(object, payload, event);
    if (this.debug) {
      console.debug(`[${this.owner}.${this.name}] ${current} -> ${transition.to} (${event})`);
    }
    return true;
  }

  reset(object) {
    object.__states.set(this.name, this.initial);
  }
}

export class EventBus {
  constructor() {
    this.handlers = new Map();
  }

  on(name, handler) {
    if (!this.handlers.has(name)) this.handlers.set(name, new Set());
    this.handlers.get(name).add(handler);
    return () => this.off(name, handler);
  }

  off(name, handler) {
    const handlers = this.handlers.get(name);
    if (handlers) handlers.delete(handler);
  }

  emit(name, payload) {
    const handlers = this.handlers.get(name);
    if (!handlers) return 0;
    for (const handler of Array.from(handlers)) handler(payload);
    return handlers.size;
  }
}

ObjectRegistry.global = new ObjectRegistry();
UmlObject.registry = ObjectRegistry.global;

const UmlRuntime = {
  ObjectRegistry,
  UmlObject,
  Association,
  StateMachine,
  EventBus,
  parseMultiplicity,
};

if (typeof module !== "undefined" && module.exports) module.exports = UmlRuntime;
if (typeof window !== "undefined") window.UmlRuntime = UmlRuntime;

export { UmlRuntime };
