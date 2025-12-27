FROM node:25-alpine

WORKDIR /app/web

# Copy web app files
COPY web/package.json web/tsconfig.json web/next.config.ts web/next-env.d.ts ./
COPY web/src ./src
COPY web/public ./public

# Create a clean package.json without workspace deps for initial install
RUN node -e "const pkg = require('./package.json'); const deps = {...pkg.dependencies}; delete deps['@dock108/js-core']; delete deps['@dock108/ui']; delete deps['@dock108/ui-kit']; pkg.dependencies = deps; pkg.scripts.dev = 'next dev -p 3000 -H 0.0.0.0'; require('fs').writeFileSync('./package.json', JSON.stringify(pkg, null, 2));"

# Install core dependencies
RUN npm install --legacy-peer-deps

# Copy workspace packages directly into node_modules
COPY packages/js-core ./node_modules/@dock108/js-core
COPY packages/ui ./node_modules/@dock108/ui
COPY packages/ui-kit ./node_modules/@dock108/ui-kit

# Show what we have
RUN echo "=== @dock108 packages ===" && ls -la node_modules/@dock108/

EXPOSE 3000

CMD ["npm", "run", "dev"]
