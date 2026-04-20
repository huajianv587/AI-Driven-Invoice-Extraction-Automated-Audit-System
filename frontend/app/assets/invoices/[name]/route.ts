import { readFile } from "node:fs/promises";
import path from "node:path";

const invoiceAssets: Record<string, string> = {
  "sample-1.jpg": "invoice.jpg",
  "sample-2.jpg": "in2.jpg",
  "sample-3.jpg": "发票3.jpg"
};

export async function GET(_request: Request, context: { params: Promise<{ name: string }> }) {
  const { name } = await context.params;
  const assetName = invoiceAssets[name];

  if (!assetName) {
    return new Response("Invoice asset not found.", { status: 404 });
  }

  const filePath = path.resolve(process.cwd(), "..", "invoices", assetName);
  const file = await readFile(filePath);
  return new Response(file, {
    headers: {
      "Cache-Control": "public, max-age=3600",
      "Content-Type": "image/jpeg"
    }
  });
}
