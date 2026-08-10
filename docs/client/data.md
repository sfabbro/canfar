# Data Access

Read and write CANFAR VOSpace Services from Python. `canfar` resolves the
endpoints and credentials; [`vosfs`](https://github.com/shinybrar/vosfs) is the
[fsspec](https://filesystem-spec.readthedocs.io/) filesystem that talks to them,
so every tool that already speaks fsspec — astropy, pandas, dask, zarr — works
without an adapter.

The same Storage Identifiers the CLI uses are importable by name.

## Open a VOSpace Service

Import a Storage Identifier and you get a ready, authenticated filesystem. Run
`canfar login` first; the credential resolution is the same one the CLI uses.

```python
from canfar.storage import arc, vault, local
```

Any configured Storage Identifier works this way. To see which are available:

```python
from canfar.storage import identifiers

identifiers()      # ['arc', 'vault', 'local']
```

Import binds the filesystem once, which is what you usually want. To build one
explicitly — to override a credential, or to name an identifier held in a
variable — use `filesystem`:

```python
from canfar.storage import filesystem

vault = filesystem("vault")
staging = filesystem("vault", token="...")        # runtime bearer token
archive = filesystem("arc", certificate="/path/to/proxy.pem")
```

`local` is reserved for the machine your code runs on and needs no credential.

## Filesystem operations

The object is a standard fsspec filesystem, so the usual verbs apply:

```python
cutouts = "/ALMA/test-data/cutouts"
target = f"{cutouts}/test-4d-cube-cutout.fits"

vault.ls(cutouts, detail=False)      # ['/ALMA/.../test-4d-cube-cutout.fits', ...]
vault.info(target)["size"]           # 169920
vault.exists(target)                 # True
vault.isdir(cutouts)                 # True
vault.glob(f"{cutouts}/*cutout.fits")
vault.find(cutouts)                  # recursive listing
vault.du(cutouts)                    # 3712320
```

Reads come in whole-object, ranged, and file-like forms:

```python
whole = vault.cat_file(target)                       # 169920 bytes
header = vault.cat_file(target, 0, 2880)             # first 2880 bytes only
first, second = vault.cat_ranges([target, target], [0, 100], [80, 180])

with vault.open(target, "rb") as handle:
    handle.read(80)

vault.head(target, 100)
vault.tail(target, 100)
```

Writes use `put_file`, `pipe_file`, `mkdir`, and `rm`. Directory listings are
cached in memory for the lifetime of the filesystem object, so a long-lived
object can serve a stale listing; build a fresh one, or pass
`use_listings_cache=False`, when you need to observe another writer's changes.

## Get a local path

Some libraries want a real path rather than a file object — anything that
memory-maps, or a C extension that opens by name. Materialise the file:

```python
vault.get_file(target, "/scratch/cutout.fits")
```

`get_file` is the standard fsspec verb; `put_file` is its counterpart for
uploads.

## Cache

Nothing is cached to disk unless you ask. On a CANFAR session `/scratch` is
fast local NVMe, is not backed up, and is cleared when the session ends, which
is exactly what a cache wants. Locally, any directory works.

### Whole files

```python
from fsspec.implementations.cached import WholeFileCacheFileSystem

cached = WholeFileCacheFileSystem(fs=vault, cache_storage="/scratch/vault-cache")

cached.cat_file(target)   # cold: fetched over the network
cached.cat_file(target)   # warm: served from /scratch
```

A cold read of the 166 KiB cutout took 2.96 s; the warm read took 0.4 ms.

Use `SimpleCacheFileSystem` when you do not need the expiry and staleness
metadata `WholeFileCacheFileSystem` keeps. Passing `cache_storage` a list of
directories tries each in order and treats only the last as writable, so a
shared read-only cache can back your own.

### Byte ranges

`vosfs` sends an HTTP `Range` header and uses the response when the byte
endpoint answers `206`, so a partial read transfers only the bytes you asked
for. Support is per-backend:

| Storage Identifier | Backend | Ranged reads |
| --- | --- | --- |
| `vault` | `minoc` | Yes — a partial read returns `206` and transfers only that slice |
| `arc` | Cavern | No — the whole object is fetched and sliced, correct but not cheaper |

Against `vault`, cache blocks instead of whole files when you touch small parts
of a large cube. `MMapCache` keeps fetched blocks in a sparse file:

```python
from fsspec.caching import MMapCache

cube = "/ALMA/test-data/cutouts/test-4d-cube.fits"
size = vault.info(cube)["size"]

blocks = MMapCache(
    blocksize=1 << 20,
    fetcher=lambda start, end: vault.cat_file(cube, start, end),
    size=size,
    location="/scratch/vault-cache/cube.blocks",
)

header = blocks._fetch(0, 2880)   # one ranged request, one block of four
```

Reading a FITS header from the 3.4 MB cube materialises one block of four. The
saving is in bytes transferred rather than seconds on small files, because
VOSpace transfer negotiation dominates a short request; it grows with file
size. Against `arc` a block cache still costs a whole download per block, so
cache whole files there.

### RAM

Omit `location` and `MMapCache` uses an anonymous memory map — a RAM cache that
never touches disk, for when `/scratch` is absent or you want the data gone
when the process exits:

```python
blocks = MMapCache(
    blocksize=1 << 20,
    fetcher=lambda start, end: vault.cat_file(cube, start, end),
    size=size,
)
```

A warm re-read of a cached range returned in 18 µs.

### What does not work

`blockcache` (`CachingFileSystem`) cannot wrap a VOSpace Service. `Range` is
honoured for byte reads, not through the file-object path:

```text
AttributeError: 'StagedReadFile' object has no attribute 'blocksize'
```

Stacked caches do not help either: chaining them (`filecache::simplecache::`)
builds the layers, but the inner layer is never filled and never serves. Use
exactly one cache layer, on your fastest local disk.

## Scientific tools

### astropy

Read a header without downloading the file, using one ranged request:

```python
from astropy.io import fits

raw = vault.cat_file(target, 0, 2880)
header = fits.Header.fromstring(raw.decode("latin-1"))
header["NAXIS"], header["OBJECT"]    # 4, 'hers1'
```

Or hand the file object straight to astropy:

```python
with vault.open(target, "rb") as handle, fits.open(handle) as hdul:
    hdul[0].data.shape      # (1, 96, 26, 16)
```

To memory-map, materialise the file first — `memmap=True` needs a real path:

```python
vault.get_file(target, "/scratch/cutout.fits")

with fits.open("/scratch/cutout.fits", memmap=True) as hdul:
    data = hdul[0].data     # paged in on demand, not loaded up front
```

### numpy

```python
import numpy as np

raw = vault.cat_file(target)
values = np.frombuffer(raw[2880:2880 + 64], dtype=">f4")
```

### pandas

Astronomy tables usually arrive as FITS rather than CSV. Read one remotely and
convert:

```python
from astropy.table import Table

with vault.open("/APASS/north/091106/n091106.0101.cat", "rb") as handle:
    table = Table.read(handle, format="fits")

frame = table.to_pandas()    # 2373 rows
frame.columns[:3]            # ['NUMBER', 'MAG_AUTO', 'MAGERR_AUTO']
```

For delimited text, pass the file object to pandas directly:

```python
import pandas as pd

with vault.open("/path/to/table.csv", "rb") as handle:
    frame = pd.read_csv(handle)
```

### dask

Memory-map a materialised cube and chunk it, so only the blocks a computation
touches are paged in:

```python
import dask.array as da
from astropy.io import fits

with fits.open("/scratch/cutout.fits", memmap=True) as hdul:
    array = da.from_array(hdul[0].data, chunks=(1, 24, 26, 16))
    array.mean().compute()
```

## Async

Every read has an async twin. Build the filesystem with `asynchronous=True`,
use the underscore-prefixed coroutines, and close it when done:

```python
import asyncio

from canfar.models.config import Configuration
from vosfs import VOSpaceFileSystem


async def main() -> None:
    config = Configuration()
    service = config.servers["canfar"].storage["vault"]
    vault = VOSpaceFileSystem(
        str(service.url),
        certfile=str(config.get_credential("cadc").path),
        asynchronous=True,
    )
    try:
        entries = await vault._ls(cutouts, detail=False)
        header = await vault._cat_file(cube, 0, 2880)
    finally:
        await vault.aclose()


asyncio.run(main())
```

Async filesystems cannot open file objects — `open()` is rejected, and the
fsspec caches are synchronous — so use the synchronous form for caching and for
libraries that want a file handle.
