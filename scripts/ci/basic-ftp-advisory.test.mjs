import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { once } from "node:events";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import net from "node:net";
import path from "node:path";
import process from "node:process";
import test from "node:test";

// Resolve the actual @lhci/cli -> proxy-agent -> pac-proxy-agent -> get-uri caller.
// These tests never contact an external FTP server or use real credentials.
const require = createRequire(import.meta.url);
const cli = createRequire(require.resolve("@lhci/cli/package.json"));
const proxy = createRequire(cli.resolve("proxy-agent"));
const pac = createRequire(proxy.resolve("pac-proxy-agent"));
const uri = createRequire(pac.resolve("get-uri"));
const ftpMain = uri.resolve("basic-ftp");
const ftp = createRequire(ftpMain);
const { Client, parseList } = uri("basic-ftp");
const { getUri } = pac("get-uri");
const stamp = new Date("2020-01-01T00:00:00Z");

async function fixture(t, { fallback = false, legacy = false } = {}) {
  const sockets = new Set(),
    servers = new Set(),
    commands = [];
  const listen = async (server) => {
    servers.add(server);
    server.on("connection", (socket) => {
      sockets.add(socket);
      socket.on("close", () => sockets.delete(socket));
      socket.on("error", () => {});
    });
    server.listen(0, "127.0.0.1");
    await once(server, "listening");
    return server.address().port;
  };
  t.after(async () => {
    for (const socket of sockets) socket.destroy();
    await Promise.all(
      [...servers].map((server) => new Promise((resolve) => server.close(resolve))),
    );
  });
  const control = net.createServer((socket) => {
    socket.write("220 disposable fixture\r\n");
    let buffer = "",
      dataSocket;
    socket.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      let end;
      while ((end = buffer.indexOf("\r\n")) !== -1) {
        const line = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const command = line.split(" ")[0].toUpperCase();
        commands.push(command);
        if (command === "USER") socket.write("331 fixture password required\r\n");
        else if (command === "PASS") socket.write("230 fixture login\r\n");
        else if (command === "FEAT")
          socket.write(
            legacy ? "211 End\r\n" : "211-Features\r\n MLST type*;size*;modify*;\r\n211 End\r\n",
          );
        else if (command === "MDTM")
          socket.write(
            line.includes("missing")
              ? "550 missing fixture\r\n"
              : fallback
                ? "500 MDTM unsupported\r\n"
                : "213 20200101000000\r\n",
          );
        else if (command === "EPSV") {
          const data = net.createServer((incoming) => {
            dataSocket = incoming;
          });
          listen(data).then(
            (port) => socket.write(`229 Entering Extended Passive Mode (|||${port}|)\r\n`),
            () => socket.destroy(),
          );
        } else if (["MLSD", "LIST", "RETR"].includes(command)) {
          assert.ok(dataSocket, "Owned data connection must precede transfer");
          socket.write("150 fixture transfer\r\n");
          const body =
            command === "RETR"
              ? "fixture"
              : legacy
                ? "-rw-r--r-- 1 owner group 7 Jan 1 2020 fixture.txt\r\n"
                : "type=file;size=7;modify=20200101000000; fixture.txt\r\n";
          dataSocket.end(body, () => socket.write("226 fixture complete\r\n"));
        } else if (command === "QUIT") socket.end("221 fixture goodbye\r\n");
        else socket.write("200 fixture option\r\n");
      }
    });
  });
  const port = await listen(control);
  return {
    url: `ftp://fixture-user:fixture-password@127.0.0.1:${port}/fixture.txt`,
    commands,
    port,
  };
}

async function contents(stream) {
  let result = "";
  for await (const chunk of stream) result += chunk.toString("utf8");
  return result;
}

test("the real get-uri caller resolves only patched basic-ftp", () => {
  const pkg = JSON.parse(readFileSync(path.join(path.dirname(ftpMain), "../package.json"), "utf8"));
  assert.equal(pkg.version, "6.2.1");
  assert.equal(typeof Client, "function");
  for (const method of ["access", "lastMod", "list", "downloadTo", "close"])
    assert.equal(typeof Client.prototype[method], "function");
});

test("normal Unix and MLSD listings preserve caller-visible fields", () => {
  const unix = parseList("-rw-r--r-- 1 owner group 7 Jan 1 2020 fixture.txt\r\n")[0];
  assert.equal(unix.name, "fixture.txt");
  assert.equal(unix.size, 7);
  assert.equal(unix.user, "owner");
  const mlsd = parseList("type=file;size=7;modify=20200101000000; fixture.txt\r\n")[0];
  assert.equal(mlsd.name, "fixture.txt");
  assert.equal(+mlsd.modifiedAt, +stamp);
});

test("GHSA-c475 malformed Unix listing terminates in a bounded child", { timeout: 4000 }, () => {
  const script = `const {parseList}=require(${JSON.stringify(ftpMain)}); const bad='-rw-r--r-- 1 '+'a '.repeat(65536)+'!'; const good='-rw-r--r-- 1 owner group 7 Jan 1 2020 fixture.txt'; console.log(JSON.stringify(parseList(bad+'\\r\\n'+good+'\\r\\n').map(x=>x.name)));`;
  const output = execFileSync(process.execPath, ["-e", script], {
    timeout: 1500,
    maxBuffer: 4096,
    encoding: "utf8",
  });
  assert.deepEqual(JSON.parse(output), ["fixture.txt"]);
});

test(
  "get-uri downloads through the patched Client and preserves lastModified",
  { timeout: 5000 },
  async (t) => {
    const server = await fixture(t);
    const stream = await getUri(server.url);
    assert.equal(+stream.lastModified, +stamp);
    assert.equal(await contents(stream), "fixture");
    assert.ok(server.commands.includes("MDTM") && server.commands.includes("RETR"));
  },
);

test(
  "get-uri preserves MLSD listing fallback when MDTM is unavailable",
  { timeout: 5000 },
  async (t) => {
    const server = await fixture(t, { fallback: true });
    const stream = await getUri(server.url);
    assert.equal(+stream.lastModified, +stamp);
    assert.equal(await contents(stream), "fixture");
    assert.ok(
      server.commands.includes("MDTM") &&
        server.commands.includes("MLSD") &&
        server.commands.includes("RETR"),
    );
  },
);

test(
  "Client.list parses a real legacy LIST without inventing a timestamp",
  { timeout: 5000 },
  async (t) => {
    const server = await fixture(t, { legacy: true });
    const client = new Client(1000);
    t.after(() => client.close());
    await client.access({
      host: "127.0.0.1",
      port: server.port,
      user: "fixture-user",
      password: "fixture-password",
    });
    const listing = await client.list("/");
    assert.equal(listing.length, 1);
    assert.equal(listing[0].name, "fixture.txt");
    assert.equal(listing[0].size, 7);
    assert.equal(listing[0].rawModifiedAt, "Jan 1 2020");
    assert.equal(listing[0].modifiedAt, undefined);
    assert.ok(server.commands.includes("LIST") && !server.commands.includes("MLSD"));
  },
);

test(
  "get-uri retains its existing ENOTFOUND limit for timestamp-less legacy LIST",
  { timeout: 5000 },
  async (t) => {
    const server = await fixture(t, { fallback: true, legacy: true });
    await assert.rejects(getUri(server.url), { code: "ENOTFOUND" });
    assert.ok(server.commands.includes("MDTM") && server.commands.includes("LIST"));
    assert.ok(!server.commands.includes("MLSD") && !server.commands.includes("RETR"));
  },
);

test(
  "get-uri missing and unchanged-resource errors remain distinct",
  { timeout: 5000 },
  async (t) => {
    const server = await fixture(t);
    await assert.rejects(getUri(server.url.replace("fixture.txt", "missing.txt")), {
      code: "ENOTFOUND",
    });
    await assert.rejects(getUri(server.url, { cache: { lastModified: stamp } }), {
      code: "ENOTMODIFIED",
    });
    assert.ok(!server.commands.includes("RETR"));
  },
);

test("default separate-transfer-host refusal happens before any socket connection", async (t) => {
  const client = new Client();
  t.after(() => client.close());
  assert.equal(client.options.allowSeparateTransferHost, false);
  let connects = 0;
  // Safety negative control: no real connection can occur even if the guard regresses.
  t.mock.method(net.Socket.prototype, "connect", () => {
    connects++;
    throw new Error("Test forbids socket connections");
  });
  const { enterPassiveModeIPv4_forceControlHostIP } = ftp("./transfer");
  await assert.rejects(
    enterPassiveModeIPv4_forceControlHostIP({
      socket: { remoteAddress: "127.0.0.1" },
      request: async (command) => {
        assert.equal(command, "PASV");
        return { message: "227 Entering Passive Mode (192,0,2,1,12,34)" };
      },
    }),
    /PASV returned another host \(192\.0\.2\.1\)/,
  );
  assert.equal(connects, 0);
});
