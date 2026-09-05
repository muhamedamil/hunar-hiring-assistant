function requiredPublicEnv(
  name: "NEXT_PUBLIC_API_BASE_URL",
  value: string | undefined,
): string {
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value.replace(/\/$/, "");
}

export const publicEnv = {
  apiBaseUrl: requiredPublicEnv(
    "NEXT_PUBLIC_API_BASE_URL",
    process.env.NEXT_PUBLIC_API_BASE_URL,
  ),
};
