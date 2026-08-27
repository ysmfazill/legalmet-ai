import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

export interface Column<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  align?: 'right' | 'center';
  width?: string;
}

/** Generic, presentational table. Empty handling is left to the caller. */
export function DataTable<Row>({
  columns,
  rows,
  getRowId,
  onRowClick,
  ariaLabel,
}: {
  columns: Column<Row>[];
  rows: Row[];
  getRowId: (row: Row) => string;
  onRowClick?: (row: Row) => void;
  ariaLabel?: string;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table" style={{ width: '100%' }} aria-label={ariaLabel}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: c.align, width: c.width }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={getRowId(row)}
              className={cn(onRowClick && 'is-clickable')}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align }}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
