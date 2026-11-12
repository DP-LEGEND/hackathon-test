import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    if (!body.input?.trim()) {
      return NextResponse.json(
        { error: "Input is required" },
        { status: 400 }
      );
    }

    return NextResponse.json({
      result: `Received: ${body.input}`,
    });
  } catch {
    return NextResponse.json(
      { error: "Something went wrong" },
      { status: 500 }
    );
  }
}