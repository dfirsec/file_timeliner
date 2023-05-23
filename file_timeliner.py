"""Create a timeline of files in a folder."""

import argparse
import contextlib
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from plotly import graph_objects as go
from plotly import io as pio


def get_stat(filepath: Path, human_readable: bool) -> list:
    """Get stat information from a filepath.

    Args:
        filepath (Path): Path of the file to get stat information from.
        human_readable (bool): If True, convert timestamps to human readable format.

    Returns:
        List: (PATH, SIZE, Access Time, Modified Time, Change Time)
    """
    try:
        stat = filepath.lstat()
    except Exception:
        logging.exception(f"Error getting stat information from {filepath}")
        return []

    if human_readable:
        atime = datetime.fromtimestamp(stat.st_atime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        ctime = datetime.fromtimestamp(stat.st_ctime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    else:
        atime = stat.st_atime
        mtime = stat.st_mtime
        ctime = stat.st_ctime

    return [
        filepath,
        stat.st_size,
        atime,
        mtime,
        ctime,
    ]


def create_graph(file_metadata: list, sort_header: str, headers: list) -> None:
    """This function creates a scatter plot using data from a file, sorted by a specified header.

    Args:
        file_metadata (list): information about files, including their paths, sizes, and timestamps.
        sort_header (str): The column header by which the data in the graph will be sorted.
        headers (list): A list of column headers for the file_metadata.
    """
    dataframe = convert_path_to_string(file_metadata, headers)
    columns = ["Access Time", "Modified Time", "Change Time"]

    if isinstance(dataframe[sort_header][0], int | float):
        for col in columns:
            with contextlib.suppress(ValueError):
                dataframe[col] = pd.to_datetime(dataframe[col].astype(float), unit="s", origin="unix")
    else:
        dataframe["Modified Time"] = pd.to_datetime(dataframe["Modified Time"], unit="s")
        for col in columns:
            dataframe[col] = pd.to_datetime(dataframe[col])

    scatter_plot_template(dataframe, sort_header)


def convert_path_to_string(file_metadata: list, headers: list) -> pd.DataFrame:
    """Converts the Path object in the file_metadata to a string.

    Args:
        file_metadata (list): information about files, including their paths, sizes, and timestamps.
        headers (list): A list of column headers for the file_metadata.

    Returns:
        pd.DataFrame: A pandas DataFrame containing information about files,
        including their paths, sizes, and  timestamps.
    """
    dataframe = pd.DataFrame(file_metadata, columns=headers)
    dataframe["Path"] = dataframe["Path"].astype(str)
    dataframe["Size"] = dataframe["Size"].astype(float)
    return dataframe


def scatter_plot_template(df: pd.DataFrame, sort_header: str) -> go.Figure:
    """Creates a scatter plot using data from a dataframe and displays it using Plotly.

    Args:
        df (pd.DataFrame):
          A pandas DataFrame containing information about files, including their paths, sizes, and
            timestamps.
        sort_header (str):
          The column header in the DataFrame that will be used to sort the data.

    Returns:
        Plotly figure object.
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
                "<b>Access Time</b>: %{customdata[0]}<br>"
                "<b>Modified Time</b>: %{customdata[1]}<br>"
                "<b>Change Time</b>: %{customdata[2]}<br>"
            ),
            customdata=df[["Access Time", "Modified Time", "Change Time"]],
        ),
    )

    fig.update_layout(title="File Timeline", xaxis_title=sort_header, yaxis_title="Size")
    pio.show(fig)
    return fig


def sort_argument_to_header(arg: str) -> str:
    """Returns a corresponding header string for sorting based on the argument.

    Args:
        arg (str): A string representing the sort argument to be converted to a header.

    Returns:
        A string that corresponds to the header name for a given sort argument. If the argument is
        "atime", the function returns "Access Time". If the argument is "mtime", the function returns
        "Modified Time". If the argument is "ctime", the function returns "Change Time".

    Raises:
        ValueError: If the argument is not "atime", "mtime", or "ctime".
    """
    labels = {"atime": "Access Time", "mtime": "Modified Time", "ctime": "Change Time"}
    try:
        return labels[arg]
    except KeyError as err:
        message = "Invalid argument. Must be 'atime', 'mtime', or 'ctime'."
        raise ValueError(message) from err


def sort_key(file_info: list[str | float], sort_index: int) -> str:
    """Get the sorting key for a file metadata entry based on the sort_index.

    Args:
        file_info (list[str | float]): A list containing file metadata.
        sort_index (int): The index of the file_info list to use as the sorting key.

    Returns:
        str: The sorting key, formatted as a string, based on the value at sort_index
    """
    value = file_info[sort_index]
    if isinstance(value, float):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return value


def main(args: argparse.Namespace) -> None:
    """Main function that takes in arguments.

    Searches for files in a directory, extracts metadata from them, sorts the metadata
    based on user input, and writes the metadata to a CSV file.

    Args:
        args (argparse.Namespace): Contains the command-line arguments passed to the script.
    """
    args.output = Path(args.output) if args.output else Path(__file__).parent / "filetimeline.csv"
    if not Path(args.PATH).exists():
        print("Directory does not exist")
        sys.exit(1)

    headers = [
        "Path",
        "Size",
        "Access Time",
        "Modified Time",
        "Change Time",
    ]

    print("\033[92m[1]\033[00m Collecting file metadata...")
    file_metadata = []
    for entry in Path(args.PATH).rglob("*" + ("/*" * args.max_depth) if args.max_depth is not None else "*"):
        if entry.is_file():
            if args.filter_extension and not entry.name.endswith(args.filter_extension):
                continue
            objstats = get_stat(entry, args.human_readable)
            if objstats:
                file_metadata.append(objstats)

    if args.sort:
        sort_header = sort_argument_to_header(args.sort)
        sort_index = headers.index(sort_header)
        file_metadata.sort(key=lambda file_info: sort_key(file_info, sort_index))

    count = 0
    with open(args.output, "a+", newline="", encoding="utf-8") as fout:
        writer = csv.writer(fout, delimiter="|")
        writer.writerow(headers)
        for metadata in file_metadata:
            writer.writerow([str(file) for file in metadata])
            count += 1
    print(f"  -> Metadata collected on {count} files written to: {args.output}")

    print("\033[92m[2]\033[00m Creating graph...")
    if args.graph:
        sort_header = sort_argument_to_header(args.sort)
        create_graph(file_metadata, sort_header, headers)
        print("  -> Graph created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a timeline of files")
    parser.add_argument("PATH", help="Path of the folder to create the timeline")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument(
        "--graph",
        "-g",
        action="store_true",
        help="Generate a graph of file sizes over time",
    )
    parser.add_argument(
        "--human-readable",
        "-H",
        action="store_true",
        help="Display times in human-readable format",
    )
    parser.add_argument(
        "--sort",
        "-s",
        choices=["atime", "mtime", "ctime"],
        help="Sort by Access Time (atime), Modified Time (mtime), or Change Time (ctime)",
    )
    parser.add_argument(
        "--max-depth",
        "-d",
        type=int,
        help="Maximum depth of recursion in subdirectories",
    )
    parser.add_argument(
        "--filter-extension",
        "-e",
        type=str,
        help="Filter files by the specified file extension (e.g., '.txt')",
    )
    args = parser.parse_args()

    main(args)
