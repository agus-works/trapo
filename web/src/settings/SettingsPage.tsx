import { Settings2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button } from '../components/ui/button';
import { PaneHeader } from '../components/workbench';
import type { AnnotationStyleSetting } from '../generated/model';
import { useAnnotationSettingsQuery, useUpdateAnnotationSettingsMutation } from '../queries/hooks';
import styles from './SettingsPage.module.css';

export function SettingsPage() {
  const settingsQuery = useAnnotationSettingsQuery();
  const updateSettings = useUpdateAnnotationSettingsMutation();
  const [draft, setDraft] = useState<AnnotationStyleSetting[]>([]);

  useEffect(() => {
    setDraft(settingsQuery.data?.settings ?? []);
  }, [settingsQuery.data]);

  return (
    <div className={styles.settingsPage}>
      <PaneHeader
        actions={
          <Button
            disabled={updateSettings.isPending || draft.length === 0}
            onClick={() => updateSettings.mutate({ settings: draft })}
            size="sm"
            variant="outline"
          >
            Save
          </Button>
        }
        icon={<Settings2 size={14} />}
        title="Annotation Settings"
      />
      <main className={styles.settingsBody}>
        {settingsQuery.isLoading ? (
          <div className={styles.emptyState}>Loading settings.</div>
        ) : (
          <AnnotationStyleTable settings={draft} onSettingsChange={setDraft} />
        )}
      </main>
    </div>
  );
}

function AnnotationStyleTable({
  settings,
  onSettingsChange,
}: {
  settings: AnnotationStyleSetting[];
  onSettingsChange: (settings: AnnotationStyleSetting[]) => void;
}) {
  if (settings.length === 0) {
    return <div className={styles.emptyState}>No annotation settings are available.</div>;
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.settingsTable}>
        <thead>
          <tr>
            <th>Engine</th>
            <th>Kind</th>
            <th>Stroke</th>
            <th>Fill</th>
            <th>Stroke Opacity</th>
            <th>Fill Opacity</th>
            <th>Width</th>
          </tr>
        </thead>
        <tbody>
          {settings.map((setting, index) => (
            <StyleRow
              key={`${setting.annotation_engine}:${setting.region_kind}:${setting.label}`}
              onChange={(next) =>
                onSettingsChange(
                  settings.map((item, itemIndex) => (itemIndex === index ? next : item)),
                )
              }
              setting={setting}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StyleRow({
  setting,
  onChange,
}: {
  setting: AnnotationStyleSetting;
  onChange: (setting: AnnotationStyleSetting) => void;
}) {
  return (
    <tr>
      <td>{setting.annotation_engine}</td>
      <td>{setting.region_kind}</td>
      <td>
        <input
          aria-label={`${setting.annotation_engine} ${setting.region_kind} stroke color`}
          onChange={(event) =>
            onChange({ ...setting, style: { ...setting.style, stroke_color: event.target.value } })
          }
          type="color"
          value={setting.style.stroke_color}
        />
      </td>
      <td>
        <input
          aria-label={`${setting.annotation_engine} ${setting.region_kind} fill color`}
          onChange={(event) =>
            onChange({ ...setting, style: { ...setting.style, fill_color: event.target.value } })
          }
          type="color"
          value={setting.style.fill_color}
        />
      </td>
      <td>
        <input
          max={1}
          min={0}
          onChange={(event) =>
            onChange({
              ...setting,
              style: { ...setting.style, stroke_opacity: Number(event.target.value) },
            })
          }
          step={0.05}
          type="number"
          value={setting.style.stroke_opacity}
        />
      </td>
      <td>
        <input
          max={1}
          min={0}
          onChange={(event) =>
            onChange({
              ...setting,
              style: { ...setting.style, fill_opacity: Number(event.target.value) },
            })
          }
          step={0.05}
          type="number"
          value={setting.style.fill_opacity}
        />
      </td>
      <td>
        <input
          max={8}
          min={1}
          onChange={(event) =>
            onChange({
              ...setting,
              style: { ...setting.style, stroke_width: Number(event.target.value) },
            })
          }
          step={0.5}
          type="number"
          value={setting.style.stroke_width}
        />
      </td>
    </tr>
  );
}
