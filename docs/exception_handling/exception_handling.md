# Exception handling strategy

The Edgar project uses a functional approach to error handling through the
`Result[T, E]` type pattern. All operations that can fail return Result objects
containing either success (`ok(value)`) or error (`err(message)`) states. This
eliminates exceptions in favor of explicit error propagation through the call
stack. The pattern enforces that callers must explicitly handle both success
and failure cases, leading to more robust error handling throughout the
pipeline architecture.
