import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { PageSelectOptions } from '../types';
import styles from './PdfDocumentPreview.module.css';

export function PageNavigationZones({
  activePageNo,
  nextPage,
  onPageSelect,
  previousPage,
}: {
  activePageNo: number;
  nextPage: number;
  onPageSelect: (pageNo: number, options?: PageSelectOptions) => void;
  previousPage: number;
}) {
  return (
    <>
      <button
        aria-label="Previous page"
        className={cn(styles.pageNavZone, styles.pageNavZonePrevious)}
        disabled={previousPage === activePageNo}
        onClick={() => onPageSelect(previousPage)}
        title="Previous page"
        type="button"
      >
        <ChevronLeft size={22} />
      </button>
      <button
        aria-label="Next page"
        className={cn(styles.pageNavZone, styles.pageNavZoneNext)}
        disabled={nextPage === activePageNo}
        onClick={() => onPageSelect(nextPage)}
        title="Next page"
        type="button"
      >
        <ChevronRight size={22} />
      </button>
    </>
  );
}
