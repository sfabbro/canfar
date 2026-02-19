# Software Repositories (CVMFS)

**Accessing thousands of scientific software packages through global read-only repositories.**

!!! abstract "🎯 What is CVMFS?"
    The **CernVM File System (CVMFS)** is a distributed, read-only filesystem designed to deliver software to large-scale computing environments. On CANFAR, all sessions (Notebooks, Desktops, and Batch) have access to CVMFS, providing instant access to software stacks maintained by the **Digital Research Alliance of Canada (Alliance)**.

## 🚀 Why Use CVMFS?

Traditional software management often involves complex installations, dependency conflicts, and large container images. CVMFS changes this by providing:

*   **Instant Access**: Thousands of pre-built packages are available without any installation.
*   **Consistency**: The same software environment used on Alliance clusters (like Fir or Nibi) is available directly in your CANFAR session.
*   **Resource Efficiency**: Software is downloaded on-demand and cached, keeping container images small and fast to launch.

## 🛠️ Accessing the Software

The Alliance software stack is mounted at `/cvmfs/soft.computecanada.ca/`. Accessing it is a two-step process:

1.  **Initialize the environment**: Source the profile to enable `module` commands.
2.  **Load your software**: Use `module load` to add specific packages to your path.

### Example: Before vs. After CVMFS

Suppose you need a specific Python version or a package not included in the standard `astroml` container.

=== "Step 0: Before CVMFS"
    Notice that the environment is limited to what is pre-installed in your container.
    ```bash
    # Current python version might be 3.12
    python --version
    # Output: Python 3.12.x
    ```

=== "Step 1: Enable CVMFS"
    Source the Alliance bash profile to enable the environment module system.
    ```bash
    source /cvmfs/soft.computecanada.ca/config/profile/bash.sh
    ```

=== "Step 2: Find & Load Software"
    Search for the software you need and load it.
    ```bash
    # See available python versions
    module avail python

    # Load Python 3.10
    module load python/3.10
    ```

=== "Step 3: Verification"
    Verify that your environment has changed.
    ```bash
    python --version
    # Output: Python 3.10.x
    ```

## 🔗 Learning More

The Alliance provides extensive documentation on their software environment. Since CANFAR mounts the same CVMFS repositories, these guides apply directly to your sessions:

*   **[Accessing CVMFS](https://docs.alliancecan.ca/wiki/Accessing_CVMFS)**: Technical overview of the filesystem.
*   **[Using Modules](https://docs.alliancecan.ca/wiki/Using_modules)**: Detailed guide on the `module` command (avail, load, list, purge).
*   **[Available Software](https://docs.alliancecan.ca/wiki/Available_software)**: Searchable list of the thousands of packages available via CVMFS.

!!! tip "Persistence"
    Environment changes made via `module load` are session-specific. If you want specific modules to be loaded every time you open a terminal, you can add the `source` and `module load` commands to your `~/.bashrc` file (located in `/arc/home/[user]/.bashrc`).
