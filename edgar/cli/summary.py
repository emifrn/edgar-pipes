import sys
import json
import pandas as pd

# Local modules
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_not_ok


def add_arguments(subparsers):
    """
    Add summary command to argument parser.
    """
    
    parser_summary = subparsers.add_parser("summary", help="aggregate grouped data")
    parser_summary.add_argument("--agg", choices=["count", "first", "last"], default="count", help="aggregation method (default: count)")
    parser_summary.add_argument("--cols", nargs="+", metavar='X', help="columns to include in output")
    parser_summary.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Aggregate piped data. Type-aware: handles both flat and grouped data.
    """
    
    if not cmd["data"]:
        return ok({"name": "summary", "data": []})
    
    # Detect data type and aggregate accordingly
    if cli.shared.is_grouped_data(cmd["data"]):
        result = aggregate_grouped_data(cmd["data"], args.agg)
    else:
        result = aggregate_flat_data(cmd["data"], args.agg)
    if is_not_ok(result):
        return result
    
    summary_data = result[1]
    
    # Apply column processing if specified
    if args.cols:
        result = cli.shared.process_cols(summary_data, args.cols, None)
        if is_not_ok(result):
            return result
        summary_data, _ = result[1]
    
    # Return packet format
    return ok({"name": "summary", "data": summary_data})


def aggregate_flat_data(data: list[dict], agg_func: str) -> Result[list[dict], str]:
    """
    Aggregate flat data into a single summary record.
    """

    try:
        if agg_func == "count":
            return ok([{"count": len(data)}])
        elif agg_func == "first":
            return ok([data[0]] if data else [{}])
        elif agg_func == "last":
            return ok([data[-1]] if data else [{}])
        else:
            return err(f"cli.summary: unknown aggregation function: {agg_func}")
            
    except Exception as e:
        return err(f"cli.summary: flat data aggregation failed: {e}")


def aggregate_grouped_data(data: list[dict], agg_func: str) -> Result[list[dict], str]:
    """
    Aggregate grouped data - one summary record per group.
    Arrays are flattened back to scalars during aggregation.
    """

    try:
        result = []
        
        for group_record in data:
            group_fields, array_fields = cli.shared.separate_group_and_array_fields(group_record)
            
            # Start with group fields (scalars)
            summary_record = dict(group_fields)
            
            # Apply aggregation to array fields
            if agg_func == "count":
                if array_fields:
                    # Count items in first array (all should have same length)
                    first_array = next(iter(array_fields.values()))
                    summary_record["count"] = len(first_array)
                else:
                    summary_record["count"] = 0
                    
            elif agg_func == "first":
                # Take first element from each array
                for field_name, array_values in array_fields.items():
                    summary_record[field_name] = array_values[0] if array_values else None
                    
            elif agg_func == "last":
                # Take last element from each array
                for field_name, array_values in array_fields.items():
                    summary_record[field_name] = array_values[-1] if array_values else None
                    
            else:
                return err(f"cli.summary.aggregate_grouped_data: unknown aggregation function: {agg_func}")
            
            result.append(summary_record)
        
        return ok(result)
        
    except Exception as e:
        return err(f"cli.summary.aggregate_grouped_data: grouped data aggregation failed: {e}")
