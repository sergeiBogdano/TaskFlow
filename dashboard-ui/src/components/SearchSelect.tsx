import { Select } from './Select';

export type SearchSelectOption = { value: string; label: string; description?: string; searchText?: string };
type SearchSelectProps = {
  disabled?: boolean;
  value: string;
  options: SearchSelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
};

export function SearchSelect({ options, searchPlaceholder = 'Поиск...', ...props }: SearchSelectProps) {
  return <Select {...props} options={options.map(option => ({ ...option, hint: option.description }))}
    searchPlaceholder={searchPlaceholder} clearable />;
}
