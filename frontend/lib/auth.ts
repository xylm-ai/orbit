export function saveToken(token: string) {
  localStorage.setItem("orbit_token", token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("orbit_token");
}

export function clearToken() {
  localStorage.removeItem("orbit_token");
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
