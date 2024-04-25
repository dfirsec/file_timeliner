"""File timeline analyzer."""

import argparse
import contextlib
import csv
import logging
import sys
from collections.abc import Generator
from datetime import UTC
from datetime import datetime
from pathlib import Path

import pandas as pd
from plotly import graph_objects as go
from plotly import io as pio
from rich.console import Console
from rich.prompt import Confirm

console = Console()


def get_stat(filepath: Path, human_readable: bool) -> list:
    """Get file statistics for a given filepath.

    Args:
        filepath (Path): The path to the file.
        human_readable (bool): Flag indicating whether to display times in human-readable format.

    Returns:
        list: The file metadata including filepath, size, created, modified, and access times.

    Raises:
        Exception: If there is an error getting the stat information from the filepath.
    """
    try:
        stat = filepath.lstat()
    except Exception:
        logging.exception(f"Error getting stat information from {filepath}")
        return []

    if human_readable:
        ctime = datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_ctime), UTC).strftime("%Y-%m-%d %H:%M:%S")
        mtime = datetime.fromtimestamp(stat.st_mtime, UTC).strftime("%Y-%m-%d %H:%M:%S")
        atime = datetime.fromtimestamp(stat.st_atime, UTC).strftime("%Y-%m-%d %H:%M:%S")
    else:
        ctime = getattr(stat, "st_birthtime", stat.st_ctime)
        mtime = stat.st_mtime
        atime = stat.st_atime

    return [
        filepath,
        stat.st_size,
        ctime,
        mtime,
        atime,
    ]


def create_graph(file_metadata: list, sort_header: str, headers: list, human_readable: bool) -> None:
    """Creates a graph based on file metadata.

    Args:
        file_metadata (list): The list of file metadata.
        sort_header (str): The column header to sort the data by.
        headers (list): The list of column headers.
        human_readable (bool): Flag indicating whether to display times in human-readable format.

    Returns:
        None
    """
    dataframe = convert_path_to_string(file_metadata, headers)
    columns = ["Created Time", "Modified Time", "Access Time"]

    for col in columns:
        if not human_readable:
            with contextlib.suppress(ValueError):
                dataframe[col] = pd.to_datetime(dataframe[col].astype(float), unit="s", origin="unix")
        else:
            dataframe[col] = pd.to_datetime(dataframe[col])

    scatter_plot_template(dataframe, sort_header)


def convert_path_to_string(file_metadata: list, headers: list) -> pd.DataFrame:
    """Converts file metadata to a pandas DataFrame.

    Args:
        file_metadata (list): The list of file metadata.
        headers (list): The list of column headers.

    Returns:
        pd.DataFrame: The DataFrame containing the converted file metadata.
    """
    dataframe = pd.DataFrame(file_metadata, columns=headers)
    dataframe["Path"] = dataframe["Path"].astype(str)
    dataframe["Size"] = dataframe["Size"].astype(float)
    return dataframe


def scatter_plot_template(df: pd.DataFrame, sort_header: str) -> go.Figure:
    """Creates a scatter plot of file sizes over a specified sort header.

    Args:
        df (pd.DataFrame): The DataFrame containing the file data.
        sort_header (str): The column header to sort the data by.

    Returns:
        go.Figure: The scatter plot figure.
    """
    fig = go.Figure()

    fig.add_trace(
        go.Scattergl(
            x=df[sort_header],
            y=df["Size"],
            mode="markers",
            marker={
                "color": "rgba(135, 206, 250, 0.5)",
                "line": {"color": "MediumPurple", "width": 1},
                "opacity": 0.8,
            },
            text=df["Path"],
            hovertemplate=(
                "<b>Path</b>: %{text}<br>"
                "<b>Size</b>: %{y}<br>"
                "<b>Created Time</b>: %{customdata[0]}<br>"
                "<b>Modified Time</b>: %{customdata[1]}<br>"
                "<b>Access Time</b>: %{customdata[2]}<br>"
            ),
            customdata=df[["Created Time", "Modified Time", "Access Time"]],
            name="",
        ),
    )

    fig.update_layout(title="File Timeline", xaxis_title=sort_header, yaxis_title="Size")
    pio.show(fig)
    return fig


def sort_argument_to_header(arg: str) -> str:
    """Convert the sort argument to the corresponding header label.

    Args:
        arg (str): The sort argument.

    Returns:
        str: The corresponding header label.

    Raises:
        ValueError: If the argument is not ctime, 'mtime', or 'atime'.
    """
    labels = {"ctime": "Created Time", "mtime": "Modified Time", "atime": "Access Time"}
    try:
        return labels[arg]
    except KeyError as err:
        message = "Invalid argument. Must be 'ctime', 'mtime', or 'atime'."
        raise ValueError(message) from err


def sort_key(file_info: list[str | float], sort_index: int) -> str:
    """Generate the sort key for a file_info based on the specified sort index.

    Args:
        file_info (list[str | float]): The file information.
        sort_index (int): The index of the sort header.

    Returns:
        str: The sort key.
    """
    value = file_info[sort_index]
    if isinstance(value, float):
        return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d %H:%M:%S")
    return value


def confirm_overwrite(filepath: Path) -> bool:
    """Prompt user for confirmation to overwrite a file."""
    try:
        if filepath.exists():
            return Confirm.ask("Timeline file already exists. OK to overwrite?", default=False)
    except KeyboardInterrupt:
        return False
    else:
        return True


def search_files(
    base_path: Path,
    max_depth: int | None,
    filter_extension: str | None = None,
) -> Generator[Path, None, None]:
    """Recursively searches for files in the given directory up to a maximum depth.

    Args:
        base_path (Path): The path to start searching.
        max_depth (Optional[int]): The maximum depth to search. None for unlimited depth.
        filter_extension (Optional[str]): The file extension to filter by.

    Yields:
        Path: Paths to files that match the criteria.
    """
    if max_depth is not None and max_depth < 0 and max_depth != -1:
        return

    for entry in base_path.iterdir():
        if entry.is_file() and (filter_extension is None or entry.suffix == filter_extension):
            yield entry
        elif entry.is_dir():
            yield from search_files(entry, None if max_depth in [None, -1] else max_depth - 1, filter_extension)


def write_to_csv(output_path: Path, headers: dict, file_metadata: list) -> None:
    """Write file metadata to a CSV file.

    Args:
        output_path: The path to the output CSV file.
        headers: The list of column headers.
        file_metadata: The list of file metadata.
    """
    counter = 0
    with output_path.open(mode="w", newline="", encoding="utf-8") as csvfile:
        csvwriter = csv.writer(csvfile, delimiter="|")
        csvwriter.writerow(headers)
        for metadata in file_metadata:
            csvwriter.writerow([str(file) for file in metadata])
            counter += 1
    console.print(f"  :gear: Metadata collected on {counter} files.")
    console.print(f"  :gear: Writing metadata to: [yellow]{output_path.name}[/yellow]")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Create a timeline of files")
    parser.add_argument("PATH", help="Path of the folder to create the timeline")
    parser.add_argument(
        "-o",
        "--output",
        default="default",
        help="Output file path. Defaults to 'file_timeline.csv' in the root directory.",
    )
    parser.add_argument(
        "--sort",
        "-s",
        choices=["atime", "mtime", "ctime"],
        default="atime",
        help="Sort by Access Time (atime), Modified Time (mtime), or Change Time (ctime)",
    )
    parser.add_argument(
        "--human-readable",
        "-H",
        action="store_true",
        help="Display times in human-readable format",
    )
    parser.add_argument(
        "--max-depth",
        "-d",
        default=1,
        type=int,
        help="Maximum depth of recursion in subdirectories. Set to -1 for unlimited depth.",
    )
    parser.add_argument(
        "--filter-extension",
        "-e",
        type=str,
        help="Filter files by the specified file extension (e.g., '.txt')",
    )
    return parser.parse_args()


def main(args: argparse.Namespace) -> None:
    """Run main file timeliner function.

    Args:
        args (argparse.Namespace): The command-line arguments parsed by argparse.

    Returns:
        None
    """
    root = Path(__file__).parent.resolve()
    base_path = Path(args.PATH)

    if not base_path.exists():
        print("Directory does not exist")
        sys.exit(1)

    # The headers for the CSV file
    headers = [
        "Path",
        "Size",
        "Created Time",
        "Modified Time",
        "Access Time",
    ]

    with console.status("Collecting file metadata..."):
        file_metadata = [
            get_stat(entry, args.human_readable)
            for entry in search_files(base_path, args.max_depth, args.filter_extension)
        ]

    if not file_metadata:
        print("No files found matching the criteria.")
        sys.exit(1)

    if args.sort:
        sort_header = sort_argument_to_header(args.sort)
        sort_index = headers.index(sort_header)
        file_metadata.sort(key=lambda file_info: sort_key(file_info, sort_index))

    output_path = Path(root) / "file_timeline.csv" if args.output.lower() == "default" else Path(args.output)
    if output_path.exists() and not confirm_overwrite(output_path):
        print("Operation cancelled.")
        sys.exit(1)
    write_to_csv(output_path, headers, file_metadata)

    with console.status("Creating graph..."):
        sort_header = sort_argument_to_header(args.sort)
        create_graph(file_metadata, sort_header, headers, args.human_readable)
    console.print("  :gear: Graph created.")


if __name__ == "__main__":
    args = parse_args()

    main(args)
