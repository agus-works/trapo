import { useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ScrollArea } from '../../components/ui/scroll-area';
import type { DocumentMarkdownPayload, PageMarkdownRecord } from '../../generated/model';
import styles from './MarkdownDocumentView.module.css';
import { markdownPageDomId, markdownRegionDomId, scrollToMarkdownRegion } from './markdownDom';
import { createMarkdownComponents } from './markdownHighlight';

export function MarkdownDocumentView({
  activeRegionId,
  activePageNo,
  markdown,
  loading,
  error,
  highlightQuery,
  onRegionSelect,
}: {
  activeRegionId: string | null;
  activePageNo: number;
  markdown: DocumentMarkdownPayload | null;
  loading: boolean;
  error: string | null;
  highlightQuery: string | null;
  onRegionSelect: (regionId: string) => void;
}) {
  const pages = markdown?.pages ?? [];
  const activePage = pages.find((page) => page.page_no === activePageNo) ?? null;
  const activePageHasMarkdown = activePage ? activePage.markdown_text.trim().length > 0 : false;
  const activeMarkdownPageNo = activePage?.page_no;
  useEffect(() => {
    if (activeRegionId) {
      scrollToMarkdownRegion(activeRegionId);
    }
  }, [activeRegionId]);
  useEffect(() => {
    if (!highlightQuery || activeRegionId || !activeMarkdownPageNo) {
      return;
    }
    window.setTimeout(() => {
      document.querySelector('[data-markdown-highlight="true"]')?.scrollIntoView({
        block: 'center',
        behavior: 'smooth',
      });
    }, 0);
  }, [activeMarkdownPageNo, activeRegionId, highlightQuery]);

  return (
    <div className={styles.markdownPane}>
      <ScrollArea className={styles.markdownScroll}>
        {error ? <div className={styles.emptyState}>{error}</div> : null}
        {!error && loading ? <div className={styles.emptyState}>Loading Markdown</div> : null}
        {!error && !loading && (!activePage || !activePageHasMarkdown) ? (
          <div className={styles.emptyState}>
            No Markdown has been generated for page {activePageNo}.
          </div>
        ) : null}
        {!error && activePage && activePageHasMarkdown ? (
          <div className={styles.scrollContent}>
            <MarkdownPage
              activeRegionId={activeRegionId}
              highlightQuery={highlightQuery}
              onRegionSelect={onRegionSelect}
              page={activePage}
            />
          </div>
        ) : null}
      </ScrollArea>
    </div>
  );
}

function MarkdownPage({
  activeRegionId,
  highlightQuery,
  page,
  onRegionSelect,
}: {
  activeRegionId: string | null;
  highlightQuery: string | null;
  page: PageMarkdownRecord;
  onRegionSelect: (regionId: string) => void;
}) {
  const regionLinks = mappedRegionLinks(page);
  const markdownComponents = useMemo(
    () => createMarkdownComponents(highlightQuery),
    [highlightQuery],
  );
  return (
    <section className={styles.page} id={markdownPageDomId(page.page_no)}>
      {regionLinks.length > 0 ? (
        <div className={styles.regionLinks}>
          {regionLinks.map((mapping) => (
            <button
              className={styles.regionLink}
              data-active={mapping.regionId === activeRegionId ? 'true' : 'false'}
              id={markdownRegionDomId(mapping.regionId)}
              key={mapping.regionId}
              onClick={() => onRegionSelect(mapping.regionId)}
              title={mapping.label}
              type="button"
            >
              {mapping.label}
            </button>
          ))}
        </div>
      ) : null}
      <div className={styles.markdownBody}>
        <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
          {page.markdown_text}
        </ReactMarkdown>
      </div>
    </section>
  );
}

function mappedRegionLinks(page: PageMarkdownRecord) {
  const links: Array<{ regionId: string; label: string }> = [];
  const seen = new Set<string>();
  for (const mapping of page.mappings ?? []) {
    if (seen.has(mapping.region_id)) {
      continue;
    }
    seen.add(mapping.region_id);
    links.push({
      regionId: mapping.region_id,
      label: mapping.markdown_excerpt || mapping.region_id,
    });
  }
  return links;
}
