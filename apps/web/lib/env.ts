function requiredPublicEnv(name: "NEXT_PUBLIC_API_BASE_URL"): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value.replace(/\/$/, "");
}

export const publicEnv = {
  apiBaseUrl: requiredPublicEnv("NEXT_PUBLIC_API_BASE_URL"),
};
