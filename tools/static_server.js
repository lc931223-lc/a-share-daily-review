const http = require("http");
const fs = require("fs");
const path = require("path");

const dir = path.resolve(process.argv[2] || ".");
const port = Number(process.argv[3] || 8787);
const types = {
  ".html": "text/html; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".pdf": "application/pdf",
};

http
  .createServer((req, res) => {
    let urlPath = decodeURIComponent(req.url.split("?")[0]);
    if (urlPath === "/") urlPath = "/index.html";
    const file = path.resolve(dir, "." + urlPath);
    if (!file.startsWith(dir)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }
    fs.readFile(file, (err, body) => {
      if (err) {
        res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("Not found");
        return;
      }
      res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
      res.end(body);
    });
  })
  .listen(port, "127.0.0.1", () => {
    console.log(`Serving ${dir} on http://127.0.0.1:${port}`);
  });
