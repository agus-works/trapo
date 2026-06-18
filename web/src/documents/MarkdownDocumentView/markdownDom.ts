export function markdownRegionDomId(regionId: string): string {
  return `markdown-region-${cssSafeId(regionId)}`;
}

export function markdownPageDomId(pageNo: number): string {
  return `markdown-page-${pageNo}`;
}

export function scrollToMarkdownRegion(regionId: string) {
  window.setTimeout(() => {
    document.getElementById(markdownRegionDomId(regionId))?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
      inline: 'nearest',
    });
  }, 0);
}

function cssSafeId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-');
}
