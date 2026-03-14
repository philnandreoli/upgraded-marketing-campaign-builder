import { FILTER_TABS } from "../constants/statusGroups";

/**
 * FilterTabs — horizontal scrollable tab bar for Dashboard campaign filtering.
 *
 * Props:
 *   activeTab   string  — id of the currently active tab
 *   onTabChange fn      — called with the tab id when a tab is clicked
 */
export default function FilterTabs({ activeTab, onTabChange }) {
  return (
    <div className="filter-tabs" role="tablist" aria-label="Filter campaigns">
      {FILTER_TABS.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls="campaign-tabpanel"
          className={`filter-tab${activeTab === tab.id ? " filter-tab--active" : ""}`}
          onClick={() => onTabChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
