import csv
import sys
import json
import pandas as pd
from tabulate import tabulate

# Local modules
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_not_ok


def add_arguments(subparsers):
    """
    Add group command to argument parser.
    """
    parser_group = subparsers.add_parser("group", help="group pipeline data by fields")
    parser_group.add_argument("-c", "--cols", nargs="+", metavar='X', help="columns to include in output")
    parser_group.add_argument("--by", nargs="+", required=True, metavar='X', help="fields to group by")
    parser_group.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Group piped data by specified fields.
    """
    
    if not cmd["data"]:
        return ok({"name": "group", "data": []})
    
    # Validate input is flat data (not already grouped)
    result = cli.shared.validate_data_type(cmd["data"], "group", "flat")
    if is_not_ok(result):
        return result
    
    # Group the data
    result = group_data(cmd["data"], args.by, args.cols)
    if is_not_ok(result):
        return result
    
    grouped_data = result[1]
    
    # Return packet format
    return ok({"name": "group", "data": grouped_data})


def group_data(data: list[dict], group_fields: list[str], cols_filter: list[str] = None) -> Result[list[dict], str]:
    """
    Group data by specified fields and create array fields for non-group columns.
    Handles column filtering with transparent processing.
    """
    
    df = pd.DataFrame(data)
    
    # Validate group fields exist in data
    missing_fields = [f for f in group_fields if f not in df.columns]
    if missing_fields:
        return err(f"cli.group: group fields not found: {', '.join(missing_fields)}")
    
    try:
        # Apply column processing BEFORE grouping if --cols specified
        if cols_filter:
            # Extend cols_filter to include group fields if not already present
            extended_cols = list(cols_filter)
            for field in group_fields:
                if field not in [col.rstrip('+-') for col in extended_cols]:
                    extended_cols.append(field)
            
            # Convert to list of dicts for cli.shared processing
            data_list = df.to_dict('records')
            result = cli.shared.process_cols(data_list, extended_cols, None)
            if is_not_ok(result):
                return result
            processed_data, valid_cols = result[1]
            df = pd.DataFrame(processed_data)
            
            # Only create arrays for non-group columns that were requested
            cols_to_group = [col for col in valid_cols if col not in group_fields]
        else:
            # Use all non-group columns
            cols_to_group = [col for col in df.columns if col not in group_fields]
        
        # Group the processed data
        result = []
        for group_values, group_df in df.groupby(group_fields):
            # Create record with group fields
            if len(group_fields) == 1:
                record = {group_fields[0]: group_values[0] if isinstance(group_values, tuple) else group_values}
            else:
                record = dict(zip(group_fields, group_values))
            
            # Add array fields for non-group columns
            for col in cols_to_group:
                record[col] = group_df[col].tolist()
            
            result.append(record)
        
        return ok(result)
        
    except Exception as e:
        return err(f"cli.group.group_data: grouping failed: {e}")
