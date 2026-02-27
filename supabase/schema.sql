-- Enable vector extension for embeddings
create extension if not exists vector;

-- Raw Spotify features table (Phase 1)
create table if not exists public.spotify_raw_features (
  id bigserial primary key,
  track_id text not null unique,
  track_name text not null,
  artist_name text,
  album_name text,
  popularity int,

  -- Optional audio features (may be null if endpoint unavailable)
  valence double precision,
  energy double precision,
  brightness double precision,
  danceability double precision,
  tempo double precision,
  key int,
  mode int,
  acousticness double precision,
  instrumentalness double precision,
  liveness double precision,
  speechiness double precision,

  -- Embeddings-ready fields for next phase
  text_for_embedding text,
  embedding vector(1536),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_spotify_raw_features_track_id
  on public.spotify_raw_features(track_id);

create index if not exists idx_spotify_raw_features_embedding
  on public.spotify_raw_features using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- Optional helper trigger to keep updated_at fresh
create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_spotify_raw_features_updated_at on public.spotify_raw_features;
create trigger trg_spotify_raw_features_updated_at
before update on public.spotify_raw_features
for each row execute function public.set_updated_at();

-- Compatibility view for downstream code expecting a `songs` shape
drop view if exists public.songs;
create view public.songs as
select
  track_id,
  track_name as title,
  artist_name as artist,
  valence,
  energy,
  brightness,
  tempo,
  danceability,
  key,
  mode,
  acousticness,
  instrumentalness,
  liveness,
  speechiness,
  popularity,
  album_name
from public.spotify_raw_features;

-- Deezer-only raw songs table (no DSP/librosa)
create table if not exists public.deeser_songs (
  id bigserial primary key,
  track_id text not null unique,
  title text not null,
  artist text,
  album_name text,
  popularity int,
  url text not null,
  deezer_link text,
  valence double precision,
  energy double precision,
  brightness double precision,
  danceability double precision,
  tempo double precision,
  key int,
  mode int,
  acousticness double precision,
  instrumentalness double precision,
  liveness double precision,
  speechiness double precision,
  emotion_cluster integer,
  text_for_embedding text,
  embedding vector(1536),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.deeser_songs add column if not exists valence double precision;
alter table public.deeser_songs add column if not exists energy double precision;
alter table public.deeser_songs add column if not exists brightness double precision;
alter table public.deeser_songs add column if not exists danceability double precision;
alter table public.deeser_songs add column if not exists tempo double precision;
alter table public.deeser_songs add column if not exists key int;
alter table public.deeser_songs add column if not exists mode int;
alter table public.deeser_songs add column if not exists acousticness double precision;
alter table public.deeser_songs add column if not exists instrumentalness double precision;
alter table public.deeser_songs add column if not exists liveness double precision;
alter table public.deeser_songs add column if not exists speechiness double precision;
alter table public.deeser_songs add column if not exists emotion_cluster integer;
alter table public.deeser_songs add column if not exists text_for_embedding text;
alter table public.deeser_songs add column if not exists embedding vector(1536);

create index if not exists idx_deeser_songs_track_id
  on public.deeser_songs(track_id);

drop trigger if exists trg_deeser_songs_updated_at on public.deeser_songs;
create trigger trg_deeser_songs_updated_at
before update on public.deeser_songs
for each row execute function public.set_updated_at();
