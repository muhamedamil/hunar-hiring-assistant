import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

process.env.NEXT_PUBLIC_API_BASE_URL ??= "http://localhost:8000/api/v1";

afterEach(cleanup);
