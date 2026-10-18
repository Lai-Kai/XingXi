# Serve native workspace pages from a production build

The user reports that every module now loads slowly. Native frontend logs show
`next dev --webpack`: recent cold route requests take 4–27 seconds, with nearly
all of that time in Next.js compilation. Repeated library/agent requests take
18–20 milliseconds. The host launcher currently hardcodes development mode.

Provide a reviewed patch for that external launcher. Its default start should
build the frontend and serve with `next start`; an explicit development setting
retains hot reload. Keep the existing ports, Gateway, authentication and database.
Validate the patch offline and document host activation, since the launcher lies
outside the coding environment's writable roots.
