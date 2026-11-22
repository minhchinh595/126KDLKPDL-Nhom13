export interface NavItem {
  title: string;
  href: string;
  icon: string;
  badge?: string;
  description?: string;
  disabled?: boolean;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export interface BreadcrumbPath {
  label: string;
  href?: string;
  active?: boolean;
}
