import type {
  ColumnDef,
  PaginationState,
  Table as ReactTable,
  SortingState,
} from '@tanstack/react-table';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../ui/table';
import { sortingIndicator } from '../helpers';
import styles from './DenseDataTable.module.css';

export function DenseDataTable<TData>({
  columns,
  data,
  globalFilter,
  getRowId,
  selectedId,
  onGlobalFilterChange,
  onRowSelect,
}: {
  columns: Array<ColumnDef<TData>>;
  data: TData[];
  globalFilter: string;
  getRowId: (row: TData) => string;
  selectedId?: string | null;
  onGlobalFilterChange: (value: string) => void;
  onRowSelect?: (row: TData) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const table = useReactTable({
    columns,
    data,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowId,
    getSortedRowModel: getSortedRowModel(),
    onGlobalFilterChange,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    state: { globalFilter, pagination, sorting },
  });

  return (
    <div className={styles.denseTableShell}>
      <div className={styles.denseTableToolbar}>
        <Input
          aria-label="Filter rows"
          className={styles.denseTableFilter}
          onChange={(event) => onGlobalFilterChange(event.target.value)}
          placeholder="Filter"
          value={globalFilter}
        />
        <span>{table.getFilteredRowModel().rows.length} rows</span>
      </div>
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder ? null : (
                    <button
                      className={
                        header.column.getCanSort() ? styles.tableSortButton : styles.tableHeaderText
                      }
                      disabled={!header.column.getCanSort()}
                      onClick={header.column.getToggleSortingHandler()}
                      type="button"
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {sortingIndicator(header.column.getIsSorted())}
                    </button>
                  )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length > 0 ? (
            table.getRowModel().rows.map((row) => (
              <TableRow
                className={row.id === selectedId ? styles.selectedRow : undefined}
                key={row.id}
                onClick={() => onRowSelect?.(row.original)}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length}>No rows.</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <TablePager table={table} />
    </div>
  );
}

function TablePager<TData>({ table }: { table: ReactTable<TData> }) {
  return (
    <div className={styles.denseTablePager}>
      <span>
        Page {table.getState().pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}
      </span>
      <div>
        <select
          onChange={(event) => table.setPageSize(Number(event.target.value))}
          value={table.getState().pagination.pageSize}
        >
          {[10, 25, 50, 100].map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
        <Button
          disabled={!table.getCanPreviousPage()}
          onClick={() => table.firstPage()}
          size="icon"
          variant="ghost"
        >
          <ChevronsLeft size={14} />
        </Button>
        <Button
          disabled={!table.getCanPreviousPage()}
          onClick={() => table.previousPage()}
          size="icon"
          variant="ghost"
        >
          <ChevronRight className={styles.rotate180} size={14} />
        </Button>
        <Button
          disabled={!table.getCanNextPage()}
          onClick={() => table.nextPage()}
          size="icon"
          variant="ghost"
        >
          <ChevronRight size={14} />
        </Button>
        <Button
          disabled={!table.getCanNextPage()}
          onClick={() => table.lastPage()}
          size="icon"
          variant="ghost"
        >
          <ChevronsRight size={14} />
        </Button>
      </div>
    </div>
  );
}
