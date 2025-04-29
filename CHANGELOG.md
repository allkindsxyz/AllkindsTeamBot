# Changelog

All notable changes to the Allkinds Team Bot project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Architecture documentation for better project understanding
- Development practices guide for consistent coding patterns
- Technical debt tracking system
- Pre-deployment checklist script
- Code integrity verification tool
- Comprehensive testing strategy

### Fixed
- Database connection handling for asyncio CancelledError
- Point deduction timing in match finding process
- Deep link generation for the communicator bot

## [1.0.0] - Date of Last Major Deployment

### Added
- Initial implementation of the Allkinds Team Bot
- Team creation and management functionality
- Question creation and answering
- Match finding based on user answers
- Anonymous chat functionality
- Railway deployment configuration

### Fixed
- Initial deployment issues
- Database connection stability
- Webhook configuration

## How to Update This Changelog

When making changes to the codebase, add a corresponding entry to the "Unreleased" section above.
When deploying a new version, rename the "Unreleased" section to the new version number and date,
and create a new empty "Unreleased" section.

Example:
```
## [Unreleased]

### Added
- New feature

## [1.2.0] - 2023-05-15

### Added
- Previously unreleased feature
``` 