# Power Tracks Core Package Scope

## Overview

This document defines the boundaries and scope of the `@powertracks/core` package, which serves as a reusable SDK for Power Track detection, decoding, unfolding, and storage operations.

## Package Boundaries

### Included in Core

The following modules and classes are **included** in the core package:

1. **PowerTrackDetector** (`src/PowerTrackDetector.ts`)
   - Real-time burst detection using spectral analysis
   - Rate-of-change (ROC) spike detection
   - Multi-venue feed integration
   - Event emission for candidate detection

2. **PowerTrackStorage** (`src/PowerTrackStorage.ts`)
   - SQLite-based storage for power tracks
   - Catalog management
   - Track metadata persistence
   - Implements `PowerTrackStorageLike` interface

3. **Track Decoder** (`src/decoder/trackDecoder.ts`)
   - XOR mask discovery
   - Varint decoding with zig-zag support
   - CRC-7 validation
   - Frame parsing and payload extraction

4. **Macro Stitcher** (`src/macro/macroStitcher.ts`)
   - Multi-track correlation and stitching
   - Macro track generation
   - Cross-symbol analysis

5. **Analytics** (`src/analytics/`)
   - Decodability scoring (`decodability.ts`)
   - Regime classification (`regime.ts`)

6. **Types** (`src/types.ts`)
   - TypeScript type definitions
   - Interfaces for detector, storage, and track data

### Excluded from Core

The following are **excluded** and remain in service/daemon packages:

1. **Server/API Layer** (`services/daemon/src/server.ts`)
   - Fastify HTTP server
   - REST API endpoints
   - WebSocket streaming
   - Authentication middleware

2. **Data Feed Integration** (`services/daemon/src/polygonFeed.ts`)
   - Polygon WebSocket client
   - Live feed management
   - Reconnection logic

3. **Configuration Loading** (`services/daemon/src/config.ts`)
   - YAML config file parsing
   - Environment variable loading
   - Engine-specific configuration

4. **Sinks** (`services/daemon/src/sinks/`)
   - SQLite sink implementation
   - Detection event handlers
   - Service-specific storage adapters

5. **Utilities** (`packages/core/src/utils/`)
   - `validateRealData()` now exported for shared use
   - Service-specific helpers

## Dependency Injection Points

To make core truly standalone, the following should be dependency-injected:

### 1. Storage Adapter

**Current**: Core uses `PowerTrackStorage` directly (SQLite)

**Proposed**: Accept `PowerTrackStorageLike` interface in constructor:

```typescript
interface PowerTrackStorageLike {
  storeCandidate(candidate: PowerTrackCandidate): Promise<void>;
  getCandidate(id: string): Promise<PowerTrackCandidate | null>;
  // ... other methods
}

class PowerTrackDetector {
  constructor(
    config: DetectorInitConfig,
    storage?: PowerTrackStorageLike  // Injected dependency
  ) {
    // ...
  }
}
```

### 2. Configuration

**Current**: Config passed as object, but some defaults hard-coded

**Proposed**: All configuration via constructor parameter, no env var reads:

```typescript
interface DetectorConfig {
  fft: {
    window: number;
    step: number;
    freqRange: [number, number];
    powerThresh: number;
  };
  roc: {
    threshold: number;
    timeWindow: number;
  };
  // ... other config
}

class PowerTrackDetector {
  constructor(config: DetectorConfig, storage?: PowerTrackStorageLike) {
    // No env var reads, no file system access
  }
}
```

### 3. Logging

**Current**: Uses `console.warn` and `EventEmitter` for events

**Proposed**: Accept logger interface:

```typescript
interface Logger {
  debug(message: string, ...args: any[]): void;
  info(message: string, ...args: any[]): void;
  warn(message: string, ...args: any[]): void;
  error(message: string, ...args: any[]): void;
}

class PowerTrackDetector {
  constructor(
    config: DetectorConfig,
    storage?: PowerTrackStorageLike,
    logger?: Logger  // Optional logger
  ) {
    // Use logger or fall back to console
  }
}
```

### 4. Data Validation

**Current**: `validateRealData()` shipped from `@powertracks/core` (Tests + daemon use the shared helper)

**Proposed Enhancements**:
- Accept custom validation function as dependency when consumers need stricter policies
- Provide adapter interface

```typescript
type DataValidator = (data: any, source?: string) => boolean;

class PowerTrackDetector {
  constructor(
    config: DetectorConfig,
    storage?: PowerTrackStorageLike,
    validator?: DataValidator  // Optional validator override
  ) {
    // Use validator or skip validation
  }
}
```

## Current Dependencies

### Internal Dependencies

- **No dependencies on services/daemon**: ✅ Verified (grep shows no imports)
- **No dependencies on UI packages**: ✅ Verified
- **Self-contained types**: ✅ All types in `src/types.ts`

### External Dependencies

- **Node.js built-ins**: `Buffer`, `crypto`, `events`, `fs`, `path`
- **No npm packages**: ✅ Zero external dependencies (pure core)

## Interface Contracts

### PowerTrackStorageLike

Core defines interface that storage must implement:

```typescript
export interface PowerTrackStorageLike {
  storeCandidate(candidate: PowerTrackCandidate): Promise<void>;
  getCandidate(id: string): Promise<PowerTrackCandidate | null>;
  listCandidates(filters?: StorageFilters): Promise<PowerTrackCandidate[]>;
  // ... other methods
}
```

### DetectorConfig

All configuration passed via constructor:

```typescript
export interface DetectorInitConfig {
  fft?: Partial<FFTConfig>;
  roc?: Partial<ROCConfig>;
  hybrid?: Partial<HybridConfig>;
  // ... other optional config
}
```

## Testing Isolation

### Current State

- Smoke tests use shared `validateRealData()` helper
- Tests use in-memory mocks for storage
- No direct daemon dependencies in test code

### Required Changes

1. **Ensure tests run without daemon** package installed

## Export Strategy

### Current Exports (`src/index.ts`)

```typescript
export { PowerTrackDetector } from './PowerTrackDetector';
export { PowerTrackStorage } from './PowerTrackStorage';
export * from './types';
export * from './macro/macroStitcher';
export * from './analytics/decodability';
export * from './analytics/regime';
export * from './decoder/trackDecoder';
```

### Proposed Additions

```typescript
// Validation utilities
export { validateRealData } from './utils/validateRealData';

// Storage interface (for external implementations)
export type { PowerTrackStorageLike } from './types';

// Configuration types
export type { DetectorConfig, DetectorInitConfig } from './types';
```

## NPM Package Configuration

### Current (`package.json`)

```json
{
  "name": "@powertracks/core",
  "version": "0.0.1",
  "main": "dist/index.js",
  "module": "dist/index.mjs",
  "types": "dist/index.d.ts"
}
```

### Required Updates

1. **Scoped package name**: `@powertracks/core` ✅ (already scoped)
2. **Build outputs**: ESM + CJS ✅ (already configured)
3. **Type declarations**: ✅ (already configured)
4. **README**: Need to add usage examples
5. **License**: Add license field
6. **Repository**: Add repository URL

## Integration Examples

### Standalone Usage

```typescript
import { PowerTrackDetector, PowerTrackStorage } from '@powertracks/core';
import type { Tick, DetectorConfig } from '@powertracks/core';

const config: DetectorConfig = {
  fft: { window: 60, step: 10, freqRange: [0.5, 3.0], powerThresh: 10000 },
  roc: { threshold: 0.007, timeWindow: 5 }
};

const storage = new PowerTrackStorage({ file: 'tracks.db' });
const detector = new PowerTrackDetector(config, storage);

detector.on('candidate', (candidate) => {
  console.log('Detected power track:', candidate.id);
});

// Process ticks
const tick: Tick = { timestamp: new Date(), price: 100.50, symbol: 'GME', venue: 'OTC' };
detector.processTick(tick);
```

### With Custom Storage

```typescript
import { PowerTrackDetector } from '@powertracks/core';
import type { PowerTrackStorageLike, PowerTrackCandidate } from '@powertracks/core';

class CustomStorage implements PowerTrackStorageLike {
  async storeCandidate(candidate: PowerTrackCandidate): Promise<void> {
    // Custom storage implementation
  }
  // ... implement other methods
}

const storage = new CustomStorage();
const detector = new PowerTrackDetector(config, storage);
```

## Migration Checklist

- [x] Verify no daemon dependencies in core
- [x] Port `validateRealData()` to core or provide adapter
- [x] Update smoke tests to remove daemon require
- [x] Add dependency injection for logger (PowerTrackDetector accepts custom logger instances)
- [x] Document all public APIs (README “API Reference” table)
- [x] Create README with usage examples (Quick Start + helper sections)
- [x] Update package.json with metadata (homepage/bugs, scoped repo)
- [x] Add integration tests for standalone usage (`packages/core/src/__tests__/standalone.integration.test.ts`)
- [x] Verify build outputs (ESM + CJS)
- [x] Test import in fresh Node project

## Next Steps

1. **Add documentation**: README with examples
2. **Package metadata**: Complete package.json
3. **Publish preparation**: Version, changelog, release notes
