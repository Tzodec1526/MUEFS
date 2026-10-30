export function isPublicPath(pathname: string): boolean {
  return /^\/cases\/(search|\d+)\/?$/.test(pathname) || pathname.startsWith('/courts/');
}
