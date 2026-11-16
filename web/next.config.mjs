/** The browser only ever talks to this app. Requests to /api/* are passed on to the
 *  backend, so cookies stay same-origin and no cross-origin setup is needed. */
const api = process.env.API_URL || "http://localhost:8000";

export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};
