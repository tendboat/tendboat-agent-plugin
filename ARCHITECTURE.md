# Architecture

This repository owns one installable agent-plugin package:

- host manifests;
- MCP launch configuration;
- a generated skill snapshot;
- executable and skill checksum locks;
- deterministic archive assembly;
- package-layout verification.

The checked-in source tree is binary-free. Assembly receives an executable as
an explicit input, verifies its digest, copies it to `plugin/bin/tendboat`, validates
the staged package with that executable, and writes a deterministic archive.

The package does not download source code or runtime dependencies. Its runtime
interface is the MCP server embedded in the supplied Tendboat executable.
