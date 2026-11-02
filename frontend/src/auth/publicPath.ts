export function isPublicPath(pathname: string): boolean {
  return /^\/(about|cases\/(search|\d+))\/?$/.test(pathname) || pathname.startsWith('/courts/');
}
