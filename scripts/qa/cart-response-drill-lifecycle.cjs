"use strict";

// Test-only, manifest-bound preload. It observes existing requests; no requests,
// response consumption, retries, timers, signal handlers or raw log output.
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const diagnostics = require("node:diagnostics_channel");
const { EventEmitter, errorMonitor } = require("node:events");
const { promiseHooks } = require("node:v8");
const { createRequire } = require("node:module");
const { threadId } = require("node:worker_threads");

const operations = [
  "observer",
  "pdp",
  "compiler",
  "product",
  "comparison",
  "related",
  "reviews",
  "enquiries",
];
const events = [
  "ready",
  "begin",
  "settle",
  "created",
  "sent",
  "received",
  "headers",
  "end",
  "finish",
  "error",
  "compile_ready",
  "compile_begin",
  "compile_settled",
  "compile_error",
  "observer_error",
  "limit",
];
const errors = ["none", "timeout", "refused", "reset", "name_unresolved", "aborted", "other"];
const symbol = Symbol.for("cart-drill-request-lifecycle-v1");
const own = (value, key) => {
  try {
    return Object.getOwnPropertyDescriptor(value, key)?.value;
  } catch {
    return undefined;
  }
};

function errorClass(error) {
  if (own(error, "name") === "TimeoutError") return "timeout";
  const code = own(error, "code");
  switch (code) {
    case "ETIMEDOUT":
      return "timeout";
    case "ECONNREFUSED":
      return "refused";
    case "ECONNRESET":
      return "reset";
    case "ENOTFOUND":
    case "EAI_AGAIN":
      return "name_unresolved";
    case "ABORT_ERR":
      return "aborted";
    default:
      return "other";
  }
}

function projectRecord(record) {
  const role = own(record, "role"),
    operation = own(record, "operation"),
    event = own(record, "event"),
    error = own(record, "error"),
    time = own(record, "time");
  if (
    !["sdk", "customer"].includes(role) ||
    !operations.includes(operation) ||
    !events.includes(event) ||
    !errors.includes(error) ||
    !Number.isSafeInteger(time) ||
    time < 0
  )
    return null;
  return { version: 1, role, operation, event, error, time };
}

function createObserver({
  role,
  emit,
  clock = () => Number(process.hrtime.bigint() / 1_000n),
  hostOf = (request) => http.OutgoingMessage.prototype.getHeader.call(request, "host"),
  compileModule = () => null,
  onFailure = () => {},
}) {
  if (!["sdk", "customer"].includes(role)) throw new TypeError("invalid lifecycle role");
  const requests = new WeakMap(),
    responses = new WeakMap(),
    wrapped = new WeakSet();
  let sdkActive = false,
    sdkStarted = false,
    customerActive = false,
    customerStarted = false,
    observerFailed = false;
  function fail() {
    observerFailed = true;
    try {
      onFailure();
    } catch {}
  }
  function record(operation, event, error = "none") {
    try {
      const value = projectRecord({ role, operation, event, error, time: clock() });
      if (!value) {
        fail();
        return;
      }
      emit(value);
    } catch {
      fail();
    }
  }
  function safe(callback) {
    return (...args) => {
      try {
        callback(...args);
      } catch {
        fail();
        record("observer", "observer_error");
      }
    };
  }
  function listen(emitter, event, callback) {
    // Read event payload metadata only. No data/readable listener changes stream flow.
    // errorMonitor observes without handling/suppressing an original error.
    if (emitter instanceof EventEmitter)
      emitter.once(event === "error" ? errorMonitor : event, safe(callback));
  }
  const settledPromises = new WeakSet(),
    watchedPromises = new WeakMap();
  let compileCalls = 0;
  const stopPromises =
    role === "customer"
      ? promiseHooks.onSettled(
          safe((promise) => {
            // Settlement includes rejection. Never attach then/catch to the original
            // promise: its unhandled-rejection behavior must remain intact.
            settledPromises.add(promise);
            const count = watchedPromises.get(promise) || 0;
            watchedPromises.delete(promise);
            for (let i = 0; i < count; i++) record("compiler", "compile_settled");
          }),
        )
      : () => {};
  function pdp(request, server = false) {
    if (own(request, "method") !== "GET") return false;
    if (own(request, server ? "url" : "path") !== "/en/p/smartphone-x1") return false;
    return server || hostOf(request) === "127.0.0.1:3000";
  }
  function apiOperation(request) {
    if (own(request, "method") !== "GET" || own(request, "origin") !== "http://127.0.0.1:8000")
      return null;
    const value = own(request, "path");
    if (value === "/products/smartphone-x1") return "product";
    if (value === "/products/smartphone-x1/comparison") return "comparison";
    if (value === "/products/smartphone-x1/related") return "related";
    if (value === "/enquiries") return "enquiries";
    return typeof value === "string" && value.length <= 256 && /^\/reviews(?:\?|$)/.test(value)
      ? "reviews"
      : null;
  }
  function sdkRequest(message, event) {
    if (role !== "sdk" || !sdkActive) return;
    const request = own(message, "request");
    if (!requests.has(request)) {
      if (!pdp(request)) return;
      requests.set(request, "pdp");
      listen(request, "error", (error) => {
        if (sdkActive) record("pdp", "error", errorClass(error));
      });
    }
    record("pdp", event);
  }
  function sdkHeaders(message) {
    if (role !== "sdk" || !sdkActive) return;
    const request = own(message, "request"),
      response = own(message, "response");
    if (requests.get(request) !== "pdp") return;
    record("pdp", "headers");
    listen(response, "end", () => {
      if (sdkActive) record("pdp", "end");
    });
    listen(response, "aborted", () => {
      if (sdkActive) record("pdp", "error", "aborted");
    });
    listen(response, "error", (error) => {
      if (sdkActive) record("pdp", "error", errorClass(error));
    });
  }
  function customerRequest(message) {
    if (role !== "customer") return;
    const request = own(message, "request"),
      response = own(message, "response");
    if (!pdp(request, true)) return;
    if (customerStarted) {
      if (customerActive) record("observer", "observer_error");
      return;
    }
    customerStarted = customerActive = true;
    responses.set(response, "pdp");
    record("pdp", "received");
    listen(response, "finish", () => {
      record("pdp", "finish");
      customerActive = false;
      stopPromises();
    });
    listen(response, "close", () => {
      customerActive = false;
      stopPromises();
    });
  }
  function upstream(message, event) {
    if (role !== "customer" || !customerActive) return;
    const request = own(message, "request");
    if (event === "created") {
      const operation = apiOperation(request);
      if (!operation) return;
      requests.set(request, operation);
    }
    const operation = requests.get(request);
    if (!operation || operation === "pdp") return;
    record(operation, event, event === "error" ? errorClass(own(message, "error")) : "none");
  }
  function compile(message) {
    if (role !== "customer") return;
    const constructor = compileModule(message),
      prototype = own(constructor, "prototype");
    if (!prototype || wrapped.has(prototype)) return;
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "ensurePage");
    if (
      typeof descriptor?.value !== "function" ||
      (!descriptor.configurable && !descriptor.writable)
    )
      return;
    const original = descriptor.value;
    function observed(...args) {
      let matched = false;
      try {
        const input = args[0];
        const names = [own(input, "page"), own(input, "url")];
        const appPaths = own(input, "appPaths");
        if (Array.isArray(appPaths)) {
          const length = own(appPaths, "length");
          if (Number.isSafeInteger(length))
            for (let i = 0; i < Math.min(length, 8); i++) names.push(own(appPaths, String(i)));
        }
        matched =
          customerActive &&
          names.some((value) =>
            [
              "/en/p/smartphone-x1",
              "/[locale]/p/[slug]",
              "/[locale]/p/[slug]/page",
              "/[locale]/(shop)/p/[slug]/page",
            ].includes(value),
          );
      } catch {
        record("observer", "observer_error");
      }
      if (!matched) return Reflect.apply(original, this, args);
      if (compileCalls >= 32) {
        record("observer", "observer_error");
        return Reflect.apply(original, this, args);
      }
      compileCalls++;
      record("compiler", "compile_begin");
      let result;
      try {
        result = Reflect.apply(original, this, args);
      } catch (error) {
        record("compiler", "compile_error", errorClass(error));
        throw error;
      }
      try {
        if (result instanceof Promise) {
          if (settledPromises.has(result)) record("compiler", "compile_settled");
          else watchedPromises.set(result, (watchedPromises.get(result) || 0) + 1);
        } else {
          record("observer", "observer_error");
        }
      } catch {
        record("observer", "observer_error");
      }
      return result; // Preserve original promise/result identity; no extra await.
    }
    Object.defineProperty(prototype, "ensurePage", { ...descriptor, value: observed });
    wrapped.add(prototype);
    record("compiler", "compile_ready");
  }
  const handlers = {
    "http.client.request.created": safe((message) => sdkRequest(message, "created")),
    "http.client.request.start": safe((message) => sdkRequest(message, "sent")),
    // Despite its name this channel observes received headers, not body end.
    "http.client.response.finish": safe(sdkHeaders),
    "http.server.request.start": safe(customerRequest),
    "undici:request:create": safe((message) => upstream(message, "created")),
    "undici:request:headers": safe((message) => upstream(message, "headers")),
    "undici:request:trailers": safe((message) => upstream(message, "end")),
    "undici:request:error": safe((message) => upstream(message, "error")),
    "tracing:module.require:end": safe(compile),
  };
  record("observer", "ready");
  return {
    handlers,
    capture: safe((event) => {
      if (role !== "sdk") return;
      if (event === "begin" && !sdkStarted) {
        sdkActive = sdkStarted = true;
        record("pdp", "begin");
      } else if (event === "settle" && sdkActive) {
        record("pdp", "settle");
        sdkActive = false;
      }
    }),
    failed: () => observerFailed,
  };
}

function outputDirectoryAllowed(metadata, packageMetadata, uid, gid) {
  if (
    !metadata.isDirectory() ||
    metadata.isSymbolicLink() ||
    !packageMetadata.isDirectory() ||
    packageMetadata.isSymbolicLink()
  )
    return false;
  // Preserve the hosted runner's manifest-owner/sole-drill-group contract.
  return (
    metadata.uid === uid ||
    (metadata.uid === packageMetadata.uid &&
      metadata.gid === gid &&
      (metadata.mode & 0o7777) === 0o770)
  );
}

function install() {
  const role = process.env.CART_DRILL_LIFECYCLE_ROLE;
  if (
    process.env.CART_DRILL_LOCAL !== "1" ||
    process.env.CART_DRILL_UID !== String(process.getuid()) ||
    !["sdk", "customer"].includes(role)
  )
    return;
  const root = path.resolve(__dirname, "../.."),
    output = path.join(root, "e2e/results/cart-response-drill");
  const metadata = fs.lstatSync(output);
  const packageMetadata = fs.lstatSync(root);
  if (!outputDirectoryAllowed(metadata, packageMetadata, process.getuid(), process.getgid()))
    return;
  const file = path.join(output, `private-lifecycle-${role}-${process.pid}-${threadId}.jsonl`);
  function onFailure() {
    // A separate fixed marker makes sink/clock failures visible without exporting
    // the reason or reopening an unsafe record file.
    try {
      const fd = fs.openSync(
        file + ".failed",
        fs.constants.O_WRONLY |
          fs.constants.O_CREAT |
          fs.constants.O_EXCL |
          fs.constants.O_NOFOLLOW,
        0o600,
      );
      try {
        fs.writeSync(fd, "failed\n");
      } finally {
        fs.closeSync(fd);
      }
    } catch {}
  }
  let count = 0,
    limited = false;
  function emit(record) {
    if (limited) return;
    let value = record;
    if (count >= 31) {
      value = { ...record, operation: "observer", event: "limit", error: "none" };
      limited = true;
    }
    const line = JSON.stringify(value) + "\n";
    if (Buffer.byteLength(line) > 256) throw new Error("lifecycle record bound");
    const fd = fs.openSync(
      file,
      fs.constants.O_WRONLY |
        fs.constants.O_CREAT |
        fs.constants.O_APPEND |
        fs.constants.O_NONBLOCK |
        fs.constants.O_NOFOLLOW,
      0o600,
    );
    try {
      const current = fs.fstatSync(fd);
      if (
        !current.isFile() ||
        current.uid !== process.getuid() ||
        (current.mode & 0o7777) !== 0o600 ||
        current.nlink !== 1 ||
        current.size + Buffer.byteLength(line) > 8192
      )
        throw new Error("lifecycle sink guard");
      fs.writeSync(fd, line);
      count++;
    } finally {
      fs.closeSync(fd);
    }
  }
  const observer = createObserver({
    role,
    emit,
    onFailure,
    compileModule(message) {
      const id = own(message, "id"),
        parent = own(message, "parentFilename");
      if (
        typeof id !== "string" ||
        id.length > 512 ||
        !/next-dev-server(?:\.js)?$/.test(id) ||
        typeof parent !== "string" ||
        !parent.startsWith(root + path.sep) ||
        !parent.includes("/next/dist/server/")
      )
        return null;
      const file = createRequire(parent).resolve(id);
      if (
        !file.startsWith(root + path.sep) ||
        !file.endsWith("/next/dist/server/dev/next-dev-server.js")
      )
        return null;
      // This exact manifest-bound public module's compiled default export is a
      // getter. Read that trusted export only after its original load completed.
      return require.cache[file]?.exports.default; // Never import/eagerly load Next.
    },
  });
  for (const [name, callback] of Object.entries(observer.handlers))
    diagnostics.subscribe(name, callback);
  Object.defineProperty(globalThis, symbol, {
    value: observer,
    configurable: false,
    enumerable: false,
    writable: false,
  });
}

module.exports = {
  createObserver,
  projectRecord,
  errorClass,
  outputDirectoryAllowed,
  operations,
  events,
  errors,
  symbol,
};
try {
  install();
} catch {
  /* Optional diagnostics cannot replace an original outcome. */
}
