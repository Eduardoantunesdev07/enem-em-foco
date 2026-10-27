import { env } from "cloudflare:workers";
import { handleApi } from "../../../lib/study-service.mjs";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return handleApi(request, env.DB);
}

export async function POST(request: Request) {
  return handleApi(request, env.DB);
}
