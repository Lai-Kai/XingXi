export type GlossKeyword = {
  term: string;
  meaning: string;
};

export type GlossSentence = {
  original: string;
  modern: string;
  keywords: GlossKeyword[];
  uncertain_terms: string[];
};

export type GlossLabel = {
  title: string;
  object_name: string | null;
  source_title: string | null;
  volume: string | null;
  page: string | null;
  status: "reading_aid";
  status_label: string;
  gloss: {
    original: string;
    sentences: GlossSentence[];
    notes: string[];
  };
};

export type GlossLabelInput = {
  text: string;
  title: string;
  object_name?: string;
  source_title?: string;
  volume?: string;
  page?: string;
};
