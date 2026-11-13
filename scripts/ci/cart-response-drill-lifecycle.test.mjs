import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import http from "node:http";
import diagnostics from "node:diagnostics_channel";
import { createRequire } from "node:module";
import {
  readFileSync,
  writeFileSync,
  mkdtempSync,
  mkdirSync,
  readdirSync,
  lstatSync,
  rmSync,
} from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const {
  createObserver,
  projectRecord,
  errorClass,
  outputDirectoryAllowed,
} = require("../qa/cart-response-drill-lifecycle.cjs");
const privateValue = "PRIVATE_COOKIE_TOKEN_BODY_PERSON";

function fixture(role, extra = {}) {
  const records = [];
  let time = 1000;
  const observer = createObserver({
    role,
    emit: (value) => {
      records.push(value);
      extra.onRecord?.(value);
    },
    clock: () => time,
    hostOf: (request) => request.host,
    ...extra,
  });
  const send = (name, payload) => observer.handlers[name](payload);
  return {
    observer,
    records,
    send,
    at(value) {
      time = value;
    },
  };
}
function request(overrides = {}) {
  return Object.assign(
    new EventEmitter(),
    {
      method: "GET",
      path: "/en/p/smartphone-x1",
      url: "/en/p/smartphone-x1",
      host: "127.0.0.1:3000",
      cookie: privateValue,
      body: privateValue,
    },
    overrides,
  );
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => {
    resolve = ok;
    reject = fail;
  });
  return { promise, resolve, reject };
}
const events = (records) => records.map((value) => value.event);

test("preload accepts manifest-owner drill-group directory without permission mutation", () => {
  const directory = {
    uid: 1000,
    gid: 998,
    mode: 0o40770,
    isDirectory: () => true,
    isSymbolicLink: () => false,
  };
  const root = { ...directory, gid: 1000 };
  assert.equal(outputDirectoryAllowed(directory, root, 998, 998), true);
  for (const change of [
    { uid: 1001 },
    { gid: 1001 },
    { mode: 0o40777 },
    { isSymbolicLink: () => true },
    { isDirectory: () => false },
  ]) {
    assert.equal(outputDirectoryAllowed({ ...directory, ...change }, root, 998, 998), false);
  }
});

function preloadCase(program, overrides = {}) {
  const stage = mkdtempSync(join(tmpdir(), "cart-lifecycle-preload-"));
  const helper = join(stage, "scripts/qa/cart-response-drill-lifecycle.cjs");
  const output = join(stage, "e2e/results/cart-response-drill");
  mkdirSync(join(stage, "scripts/qa"), { recursive: true });
  mkdirSync(output, { recursive: true });
  writeFileSync(
    helper,
    readFileSync(new URL("../qa/cart-response-drill-lifecycle.cjs", import.meta.url)),
  );
  try {
    const result = spawnSync(process.execPath, ["-e", program], {
      cwd: stage,
      env: {
        PATH: process.env.PATH,
        CART_DRILL_LOCAL: "1",
        CART_DRILL_UID: String(process.getuid()),
        CART_DRILL_LIFECYCLE_ROLE: "sdk",
        ...overrides,
      },
      encoding: "utf8",
      timeout: 3000,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, "");
    const files = readdirSync(output).map((name) => {
      const metadata = lstatSync(join(output, name));
      return {
        name,
        mode: metadata.mode & 0o777,
        bytes:
          metadata.isFile() && !metadata.isSymbolicLink()
            ? readFileSync(join(output, name), "utf8")
            : null,
      };
    });
    return {
      files,
      control: (() => {
        try {
          return JSON.parse(readFileSync(join(stage, "control.json"), "utf8"));
        } catch {
          return null;
        }
      })(),
      outside: (() => {
        try {
          return readFileSync(join(stage, "outside"), "utf8");
        } catch {
          return null;
        }
      })(),
    };
  } finally {
    rmSync(stage, { recursive: true, force: true });
  }
}
const captureProgram = `require('./scripts/qa/cart-response-drill-lifecycle.cjs');
const observer = Object.getOwnPropertyDescriptor(globalThis, Symbol.for('cart-drill-request-lifecycle-v1'))?.value;
observer?.capture('begin'); observer?.capture('settle');`;

test("manifest-bound preload installs only owned private fixed metadata output", () => {
  const value = preloadCase(captureProgram);
  assert.equal(value.files.length, 1);
  assert.equal(value.files[0].mode, 0o600);
  const rows = value.files[0].bytes
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  assert.deepEqual(
    rows.map((row) => row.event),
    ["ready", "begin", "settle"],
  );
  assert.ok(
    rows.every((row) => Object.keys(row).join() === "version,role,operation,event,error,time"),
  );
});
for (const override of [
  { CART_DRILL_LOCAL: "0" },
  { CART_DRILL_UID: "invalid" },
  { CART_DRILL_LIFECYCLE_ROLE: privateValue },
]) {
  test("preload refuses nonlocal, wrong-UID or unapproved-role activation", () => {
    assert.equal(preloadCase(captureProgram, override).files.length, 0);
  });
}
test("preload caps records and emits one fixed overflow marker", () => {
  const value = preloadCase(`require('./scripts/qa/cart-response-drill-lifecycle.cjs');
const observer = globalThis[Symbol.for('cart-drill-request-lifecycle-v1')]; observer.capture('begin');
const http = require('node:http'), channel = require('node:diagnostics_channel').channel('http.client.request.created');
for (let i=0;i<100;i++) { const request=new http.OutgoingMessage(); request.method='GET'; request.path='/en/p/smartphone-x1'; request.setHeader('host','127.0.0.1:3000'); channel.publish({request}); }
observer.capture('settle');`);
  const rows = value.files[0].bytes
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  assert.equal(rows.length, 32);
  assert.equal(rows.filter((row) => row.event === "limit").length, 1);
  assert.ok(Buffer.byteLength(value.files[0].bytes) <= 8192);
});
test("unsafe preload sink never reads symlink target and marks failure without raw reason", () => {
  const value = preloadCase(`const fs=require('node:fs');
fs.writeFileSync('outside', 'PRIVATE_SECRET_CONTENT');
fs.symlinkSync(process.cwd()+'/outside', 'e2e/results/cart-response-drill/private-lifecycle-sdk-'+process.pid+'-0.jsonl');
require('./scripts/qa/cart-response-drill-lifecycle.cjs');
globalThis[Symbol.for('cart-drill-request-lifecycle-v1')].capture('begin');`);
  assert.equal(value.outside, "PRIVATE_SECRET_CONTENT");
  const marker = value.files.find((file) => file.name.endsWith(".failed"));
  assert.equal(marker.bytes, "failed\n");
  assert.equal(marker.mode, 0o600);
});
test("preload observes original cached module load and its public default getter", () => {
  const value = preloadCase(
    `const fs=require('node:fs');
fs.mkdirSync('node_modules/next/dist/server/dev', {recursive:true});
fs.writeFileSync('node_modules/next/dist/server/dev/next-dev-server.js', "class Server { ensurePage(input) { return Promise.resolve(input); } } Object.defineProperty(exports,'default',{get(){return Server;}});");
fs.writeFileSync('node_modules/next/dist/server/parent.js', "module.exports=require('./dev/next-dev-server');");
require('./scripts/qa/cart-response-drill-lifecycle.cjs');
const Server=require('./node_modules/next/dist/server/parent').default;
const response=new (require('node:events').EventEmitter)();
require('node:diagnostics_channel').channel('http.server.request.start').publish({request:{method:'GET',url:'/en/p/smartphone-x1'},response});
new Server().ensurePage({page:'/[locale]/p/[slug]'}).then(()=>response.emit('finish'));`,
    { CART_DRILL_LIFECYCLE_ROLE: "customer" },
  );
  const rows = value.files[0].bytes
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  assert.deepEqual(
    rows.map((row) => row.event),
    ["ready", "compile_ready", "received", "compile_begin", "compile_settled", "finish"],
  );
});
test("unsafe preload FIFO is nonblocking and marks fixed sink failure", () => {
  const value = preloadCase(`const cp=require('node:child_process');
const target='e2e/results/cart-response-drill/private-lifecycle-sdk-'+process.pid+'-0.jsonl';
if(cp.spawnSync('mkfifo',[target]).status!==0) process.exit(1);
require('./scripts/qa/cart-response-drill-lifecycle.cjs');
globalThis[Symbol.for('cart-drill-request-lifecycle-v1')].capture('begin');`);
  assert.equal(value.files.find((file) => file.name.endsWith(".failed")).bytes, "failed\n");
  assert.equal(value.files.find((file) => file.name.endsWith(".jsonl")).bytes, null);
});
test("passive compiler settlement preserves original child unhandledRejection event", () => {
  for (const observed of [false, true]) {
    const value = preloadCase(`const fs=require('node:fs'); const error=new Error('PRIVATE');
fs.writeFileSync('control.json',JSON.stringify({event:false,same:false}));
process.once('unhandledRejection', reason => fs.writeFileSync('control.json',JSON.stringify({event:true,same:reason===error})));
class Compiler { ensurePage(){ return Promise.reject(error); } }
if (${observed}) {
 const {createObserver}=require('./scripts/qa/cart-response-drill-lifecycle.cjs');
 const observer=createObserver({role:'customer',emit:()=>{},compileModule:()=>Compiler});
 observer.handlers['tracing:module.require:end']({});
 observer.handlers['http.server.request.start']({request:{method:'GET',url:'/en/p/smartphone-x1'},response:new(require('node:events').EventEmitter)()});
}
new Compiler().ensurePage({page:'/en/p/smartphone-x1'});`);
    assert.deepEqual(value.control, { event: true, same: true });
  }
});

test("lifecycle projection emits exactly fixed own scalars and no private fields", () => {
  const input = {
    role: "sdk",
    operation: "pdp",
    event: "headers",
    error: "none",
    time: 1000,
    cookie: privateValue,
    body: privateValue,
    stack: privateValue,
    toJSON() {
      throw new Error(privateValue);
    },
  };
  const value = projectRecord(input);
  assert.deepEqual(Object.keys(value), ["version", "role", "operation", "event", "error", "time"]);
  assert.ok(!JSON.stringify(value).includes("PRIVATE"));
  let reads = 0;
  const getter = { ...input };
  Object.defineProperty(getter, "time", {
    get() {
      reads++;
      return 1000;
    },
  });
  assert.equal(projectRecord(getter), null);
  assert.equal(reads, 0);
  assert.equal(projectRecord(Object.create(input)), null);
});

for (const bad of [
  -1,
  NaN,
  Infinity,
  0.1,
  "1000",
  true,
  1n,
  Symbol("PRIVATE"),
  {
    valueOf() {
      throw new Error(privateValue);
    },
  },
]) {
  test(`lifecycle clock rejects ${typeof bad} without coercion`, () => {
    assert.equal(
      projectRecord({ role: "sdk", operation: "pdp", event: "created", error: "none", time: bad }),
      null,
    );
  });
}
for (const field of ["role", "operation", "event", "error"]) {
  test(`lifecycle closed ${field} rejects arbitrary text`, () => {
    assert.equal(
      projectRecord({
        role: "sdk",
        operation: "pdp",
        event: "headers",
        error: "none",
        time: 0,
        [field]: privateValue,
      }),
      null,
    );
  });
}
for (const [code, expected] of [
  ["ETIMEDOUT", "timeout"],
  ["ECONNREFUSED", "refused"],
  ["ECONNRESET", "reset"],
  ["ENOTFOUND", "name_unresolved"],
  ["EAI_AGAIN", "name_unresolved"],
  ["ABORT_ERR", "aborted"],
  [privateValue, "other"],
]) {
  test(`lifecycle error code maps only ${expected}`, () => {
    assert.equal(errorClass({ code, message: privateValue, stack: privateValue }), expected);
  });
}
test("lifecycle error classification invokes no getter, prototype or coercion", () => {
  let reads = 0;
  const error = {
    code: {
      toString() {
        reads++;
        return "ECONNREFUSED";
      },
    },
  };
  Object.defineProperty(error, "name", {
    get() {
      reads++;
      return "TimeoutError";
    },
  });
  assert.equal(errorClass(error), "other");
  assert.equal(reads, 0);
  assert.equal(errorClass(Object.create({ code: "ECONNRESET" })), "other");
  assert.equal(errorClass({ name: "TimeoutError", message: privateValue }), "timeout");
});

test("SDK response headers remain distinct from body end and freeze before cleanup", () => {
  const f = fixture("sdk"),
    req = request(),
    response = new EventEmitter();
  f.send("http.client.request.created", { request: req });
  assert.deepEqual(events(f.records), ["ready"]);
  f.observer.capture("begin");
  f.send("http.client.request.created", { request: req });
  f.send("http.client.request.start", { request: req });
  f.send("http.client.response.finish", { request: req, response });
  assert.equal(f.records.filter((value) => value.event === "headers").length, 1);
  assert.equal(f.records.filter((value) => value.event === "end").length, 0);
  assert.equal(response.listenerCount("data"), 0);
  assert.equal(response.listenerCount("readable"), 0);
  response.emit("end");
  f.observer.capture("settle");
  const before = f.records.length;
  response.on("error", () => {});
  req.on("error", () => {});
  response.emit("error", { code: "ECONNRESET", message: privateValue });
  req.emit("error", { code: "ECONNRESET", message: privateValue });
  f.send("http.client.request.start", { request: req });
  f.observer.capture("begin");
  assert.equal(f.records.length, before);
  assert.ok(!JSON.stringify(f.records).includes("PRIVATE"));
});
test("SDK error observation preserves unhandled error identity and listener semantics", () => {
  const f = fixture("sdk"),
    req = request();
  f.observer.capture("begin");
  f.send("http.client.request.created", { request: req });
  const error = new Error(privateValue);
  error.code = "ECONNRESET";
  assert.equal(req.listenerCount("error"), 0);
  assert.throws(
    () => req.emit("error", error),
    (value) => value === error,
  );
  assert.equal(f.records.at(-1).error, "reset");
});

for (const override of [
  { path: "/en/health" },
  { path: "/en/p/PRIVATE" },
  { path: "/en/p/smartphone-x1?token=PRIVATE" },
  { method: "POST" },
  { host: "PRIVATE:3000" },
  { host: "127.0.0.1:8000" },
]) {
  test("SDK lifecycle ignores unrelated request metadata", () => {
    const f = fixture("sdk");
    f.observer.capture("begin");
    f.send("http.client.request.created", { request: request(override) });
    assert.deepEqual(events(f.records), ["ready", "begin"]);
  });
}
test("customer SSR roles are bounded and complete independently of document body", () => {
  const f = fixture("customer"),
    req = request(),
    response = new EventEmitter();
  f.send("http.server.request.start", { request: req, response });
  for (const [pathname, expected] of [
    ["/products/smartphone-x1", "product"],
    ["/products/smartphone-x1/comparison", "comparison"],
    ["/products/smartphone-x1/related", "related"],
    ["/reviews?product_id=PRIVATE", "reviews"],
    ["/enquiries", "enquiries"],
  ]) {
    const upstream = {
      origin: "http://127.0.0.1:8000",
      path: pathname,
      method: "GET",
      headers: privateValue,
      body: privateValue,
    };
    f.send("undici:request:create", { request: upstream });
    f.send("undici:request:headers", { request: upstream, response: { headers: privateValue } });
    f.send("undici:request:trailers", { request: upstream, trailers: privateValue });
    assert.deepEqual(
      f.records.filter((value) => value.operation === expected).map((value) => value.event),
      ["created", "headers", "end"],
    );
  }
  response.emit("finish");
  const before = f.records.length;
  f.send("http.server.request.start", { request: request(), response: new EventEmitter() });
  f.send("undici:request:create", {
    request: { origin: "http://127.0.0.1:8000", path: "/enquiries", method: "GET" },
  });
  assert.equal(f.records.length, before);
  assert.ok(!JSON.stringify(f.records).includes("PRIVATE"));
});
test("customer lifecycle rejects foreign origin and auth/provider routes", () => {
  const f = fixture("customer");
  f.send("http.server.request.start", { request: request(), response: new EventEmitter() });
  for (const upstream of [
    { origin: "https://PRIVATE", path: "/enquiries", method: "GET" },
    { origin: "http://127.0.0.1:8000", path: "/auth/PRIVATE", method: "GET" },
    { origin: "http://127.0.0.1:8000", path: "/enquiries", method: "POST" },
  ])
    f.send("undici:request:create", { request: upstream });
  assert.deepEqual(events(f.records), ["ready", "received"]);
});

function compilerFixture(original) {
  class Compiler {}
  Object.defineProperty(Compiler.prototype, "ensurePage", {
    value: original,
    configurable: true,
    writable: true,
    enumerable: false,
  });
  const f = fixture("customer", { compileModule: () => Compiler });
  f.send("tracing:module.require:end", {});
  f.send("http.server.request.start", { request: request(), response: new EventEmitter() });
  return { ...f, Compiler, instance: new Compiler() };
}
test("compile observation retains receiver, exact arguments, promise and descriptor", async () => {
  const wait = deferred();
  let actualThis, actualArgs;
  const original = function (...args) {
    actualThis = this;
    actualArgs = args;
    return wait.promise;
  };
  const f = compilerFixture(original),
    input = { page: "/en/p/smartphone-x1" },
    extra = { private: privateValue };
  const result = f.instance.ensurePage(input, extra);
  assert.equal(result, wait.promise);
  assert.equal(actualThis, f.instance);
  assert.equal(actualArgs[0], input);
  assert.equal(actualArgs[1], extra);
  assert.ok(events(f.records).includes("compile_begin"));
  assert.ok(!events(f.records).includes("compile_settled"));
  wait.resolve();
  await result;
  await Promise.resolve();
  assert.ok(events(f.records).includes("compile_settled"));
  const descriptor = Object.getOwnPropertyDescriptor(f.Compiler.prototype, "ensurePage");
  assert.equal(descriptor.enumerable, false);
  assert.equal(descriptor.configurable, true);
  assert.equal(descriptor.writable, true);
  assert.ok(!JSON.stringify(f.records).includes("PRIVATE"));
});
for (const asyncFailure of [false, true]) {
  test(`compile observation retains identical ${asyncFailure ? "rejection" : "throw"}`, async () => {
    const error = new Error(privateValue);
    const f = compilerFixture(() => {
      if (asyncFailure) return Promise.reject(error);
      throw error;
    });
    if (asyncFailure)
      await assert.rejects(
        f.instance.ensurePage({ page: "/en/p/smartphone-x1" }),
        (value) => value === error,
      );
    else
      assert.throws(
        () => f.instance.ensurePage({ page: "/en/p/smartphone-x1" }),
        (value) => value === error,
      );
    assert.ok(events(f.records).includes(asyncFailure ? "compile_settled" : "compile_error"));
    assert.ok(!JSON.stringify(f.records).includes("PRIVATE"));
  });
}
test("unrelated compile calls and nonpromise results keep original behavior", () => {
  const value = {};
  let calls = 0;
  const f = compilerFixture(() => {
    calls++;
    return value;
  });
  assert.equal(f.instance.ensurePage({ page: "/en/health" }), value);
  assert.equal(events(f.records).filter((event) => event === "compile_begin").length, 0);
  assert.equal(f.instance.ensurePage({ page: "/en/p/smartphone-x1" }), value);
  assert.equal(calls, 2);
  assert.ok(events(f.records).includes("observer_error"));
});
test("hostile compile metadata cannot replace original behavior", () => {
  const revoked = Proxy.revocable([], {});
  revoked.revoke();
  const value = {};
  const f = compilerFixture(() => value);
  assert.equal(f.instance.ensurePage({ appPaths: revoked.proxy }), value);
  assert.ok(events(f.records).includes("observer_error"));
});
for (const failure of ["clock", "sink", "metadata", "resolver"]) {
  test(`optional ${failure} failure stays contained and marks coverage`, () => {
    let failures = 0;
    const extra = {
      onFailure() {
        failures++;
      },
    };
    if (failure === "clock")
      extra.clock = () => {
        throw new Error(privateValue);
      };
    if (failure === "sink")
      extra.emit = () => {
        throw new Error(privateValue);
      };
    if (failure === "metadata")
      extra.hostOf = () => {
        throw new Error(privateValue);
      };
    if (failure === "resolver")
      extra.compileModule = () => {
        throw new Error(privateValue);
      };
    const f = fixture(failure === "resolver" ? "customer" : "sdk", extra);
    assert.doesNotThrow(() => {
      f.observer.capture("begin");
      f.send("http.client.request.created", { request: request() });
      f.send("tracing:module.require:end", {});
      f.observer.capture("settle");
    });
    assert.equal(f.observer.failed(), true);
    assert.ok(failures > 0);
  });
}

test("frozen Node HTTP channels distinguish headers from body end on owned loopback", async () => {
  const header = deferred();
  const sdk = fixture("sdk", {
    hostOf: (req) => http.OutgoingMessage.prototype.getHeader.call(req, "host"),
    onRecord: (value) => {
      if (value.event === "headers") header.resolve();
    },
  });
  const customer = fixture("customer");
  const subscriptions = [];
  for (const [name, callback] of Object.entries(sdk.observer.handlers))
    if (name.startsWith("http.client")) {
      diagnostics.subscribe(name, callback);
      subscriptions.push([name, callback]);
    }
  const serverCallback = customer.observer.handlers["http.server.request.start"];
  diagnostics.subscribe("http.server.request.start", serverCallback);
  subscriptions.push(["http.server.request.start", serverCallback]);
  const received = deferred(),
    finish = deferred();
  const server = http.createServer((req, res) => {
    res.write("synthetic");
    received.resolve();
    finish.promise.then(() => res.end("done"));
  });
  let req, bound;
  try {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    sdk.observer.capture("begin");
    const ended = new Promise((resolve, reject) => {
      req = http.get(
        {
          hostname: "127.0.0.1",
          port: server.address().port,
          path: "/en/p/smartphone-x1",
          headers: { Host: "127.0.0.1:3000" },
        },
        (response) => {
          response.resume();
          response.once("end", resolve);
        },
      );
      req.once("error", reject);
    });
    ended.catch(() => {});
    await Promise.race([
      Promise.all([received.promise, header.promise]),
      new Promise((resolve, reject) => {
        bound = setTimeout(() => reject(new Error("owned HTTP test bound")), 2000);
      }),
    ]);
    assert.ok(events(sdk.records).includes("headers"));
    assert.ok(!events(sdk.records).includes("end"));
    finish.resolve();
    await ended;
    sdk.observer.capture("settle");
    assert.ok(events(sdk.records).includes("created"));
    assert.ok(events(sdk.records).includes("sent"));
    assert.ok(events(sdk.records).includes("end"));
    assert.ok(events(customer.records).includes("received"));
    assert.ok(events(customer.records).includes("finish"));
  } finally {
    clearTimeout(bound);
    finish.resolve();
    req?.destroy();
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    for (const [name, callback] of subscriptions) diagnostics.unsubscribe(name, callback);
  }
});

test("frozen Node fetch publishes own Undici role metadata on owned loopback", async () => {
  const f = fixture("customer"),
    response = new EventEmitter();
  f.send("http.server.request.start", { request: request(), response });
  const requests = new WeakMap(),
    failures = [],
    subscriptions = [];
  const server = http.createServer((req, res) => res.end("synthetic"));
  let origin;
  try {
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    origin = "http://127.0.0.1:" + server.address().port;
    for (const name of [
      "undici:request:create",
      "undici:request:headers",
      "undici:request:trailers",
    ]) {
      const callback = (message) => {
        try {
          const raw = Object.getOwnPropertyDescriptor(message, "request")?.value;
          const actualOrigin = Object.getOwnPropertyDescriptor(raw, "origin")?.value;
          if (actualOrigin !== origin) return;
          assert.equal(typeof actualOrigin, "string");
          if (!requests.has(raw)) {
            const method = Object.getOwnPropertyDescriptor(raw, "method")?.value;
            const path = Object.getOwnPropertyDescriptor(raw, "path")?.value;
            assert.equal(method, "GET");
            assert.equal(typeof path, "string");
            // Only substitute this owned ephemeral origin for the fixed fixture
            // origin; preserve the real channel's method/path/request identity.
            requests.set(raw, { method, path, origin: "http://127.0.0.1:8000" });
          }
          f.send(name, { request: requests.get(raw) });
        } catch (error) {
          failures.push(error);
        }
      };
      diagnostics.subscribe(name, callback);
      subscriptions.push([name, callback]);
    }
    for (const path of [
      "/products/smartphone-x1",
      "/products/smartphone-x1/comparison",
      "/products/smartphone-x1/related",
      "/reviews?product_id=synthetic",
      "/enquiries",
    ]) {
      const result = await fetch(origin + path, { signal: AbortSignal.timeout(2000) });
      await result.arrayBuffer();
    }
    assert.deepEqual(failures, []);
    for (const operation of ["product", "comparison", "related", "reviews", "enquiries"])
      assert.deepEqual(
        f.records.filter((record) => record.operation === operation).map((record) => record.event),
        ["created", "headers", "end"],
      );
  } finally {
    response.emit("finish");
    for (const [name, callback] of subscriptions) diagnostics.unsubscribe(name, callback);
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});

test("hosted integration uses manifest-bound preload with unchanged gates and workflow", () => {
  const shell = readFileSync(new URL("../qa/run-cart-response-drill.sh", import.meta.url), "utf8");
  const packageSource = readFileSync(
    new URL("../qa/cart-response-drill-package.py", import.meta.url),
    "utf8",
  );
  assert.match(packageSource, /"scripts\/qa\/cart-response-drill-lifecycle\.cjs",/);
  assert.match(shell, /--require "\$drill_root\/scripts\/qa\/cart-response-drill-lifecycle\.cjs"/);
  assert.match(shell, /CART_DRILL_LIFECYCLE_ROLE="\$drill_lifecycle_role"/);
  assert.doesNotMatch(shell, /NODE_OPTIONS=|--inspect|--loader/);
  assert.match(shell, /d\['request_lifecycle'\] = request_lifecycle\(\)/);
  const helper = readFileSync(
    new URL("../qa/cart-response-drill-lifecycle.cjs", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(
    helper,
    /\.on\("data"|setTimeout\(|setInterval\(|process\.on\("SIG|console\./,
  );
});
