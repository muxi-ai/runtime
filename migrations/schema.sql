--
-- PostgreSQL database dump
--

\restrict GDgFhqigmUtcU56my9PhadjkDTQG5GRvey6hV42eCvvU3XtYJOMVvPLeDwPpCRr

-- Dumped from database version 17.6 (Debian 17.6-2.pgdg13+1)
-- Dumped by pg_dump version 17.6 (Debian 17.6-2.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: nanoid(integer, text); Type: FUNCTION; Schema: public; Owner: muxi
--

CREATE FUNCTION public.nanoid(size integer DEFAULT 21, alphabet text DEFAULT '_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'::text) RETURNS text
    LANGUAGE plpgsql
    AS $$
        DECLARE
            idBuilder      text := '';
            counter        int  := 0;
            bytes          bytea;
            alphabetIndex  int;
            alphabetArray  text[];
            alphabetLength int;
            mask           int;
            step           int;
        BEGIN
            -- Split the alphabet into an array of characters
            alphabetArray := regexp_split_to_array(alphabet, '');
            alphabetLength := array_length(alphabetArray, 1);

            -- Calculate the bitmask for generating random values
            mask := (2 << CAST(FLOOR(LOG(alphabetLength - 1) / LOG(2)) AS int)) - 1;

            -- Calculate step size for generating random bytes
            step := CAST(CEIL(1.6 * mask * size / alphabetLength) AS int);

            -- Generate the ID
            WHILE true LOOP
                -- Get random bytes
                bytes := gen_random_bytes(step);

                -- Process each byte
                WHILE counter < step LOOP
                    alphabetIndex := (get_byte(bytes, counter) & mask) + 1;

                    -- Check if the index is within alphabet bounds
                    IF alphabetIndex <= alphabetLength THEN
                        idBuilder := idBuilder || alphabetArray[alphabetIndex];

                        -- Return the ID once we reach the desired length
                        IF length(idBuilder) = size THEN
                            RETURN idBuilder;
                        END IF;
                    END IF;

                    counter := counter + 1;
                END LOOP;

                counter := 0;
            END LOOP;
        END
        $$;


ALTER FUNCTION public.nanoid(size integer, alphabet text) OWNER TO muxi;

--
-- Name: update_scheduled_jobs_updated_at(); Type: FUNCTION; Schema: public; Owner: muxi
--

CREATE FUNCTION public.update_scheduled_jobs_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$;


ALTER FUNCTION public.update_scheduled_jobs_updated_at() OWNER TO muxi;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: collections; Type: TABLE; Schema: public; Owner: muxi
--

CREATE TABLE public.collections (
    id integer NOT NULL,
    user_id integer NOT NULL,
    collection_id character(21) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.collections OWNER TO muxi;

--
-- Name: collections_id_seq; Type: SEQUENCE; Schema: public; Owner: muxi
--

CREATE SEQUENCE public.collections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_id_seq OWNER TO muxi;

--
-- Name: collections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: muxi
--

ALTER SEQUENCE public.collections_id_seq OWNED BY public.collections.id;


--
-- Name: credentials; Type: TABLE; Schema: public; Owner: muxi
--

CREATE TABLE public.credentials (
    id integer NOT NULL,
    user_id integer NOT NULL,
    credential_id character(21) NOT NULL,
    name character varying(255) NOT NULL,
    service character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    credentials text NOT NULL
);


ALTER TABLE public.credentials OWNER TO muxi;

--
-- Name: credentials_id_seq; Type: SEQUENCE; Schema: public; Owner: muxi
--

CREATE SEQUENCE public.credentials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.credentials_id_seq OWNER TO muxi;

--
-- Name: credentials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: muxi
--

ALTER SEQUENCE public.credentials_id_seq OWNED BY public.credentials.id;


--
-- Name: memories; Type: TABLE; Schema: public; Owner: muxi
--

CREATE TABLE public.memories (
    id integer NOT NULL,
    user_id integer NOT NULL,
    memory_id character(21) NOT NULL,
    collection_id integer,
    content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    embedding public.vector(1536),
    source character varying(255),
    type character varying(50),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.memories OWNER TO muxi;

--
-- Name: memories_id_seq; Type: SEQUENCE; Schema: public; Owner: muxi
--

CREATE SEQUENCE public.memories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.memories_id_seq OWNER TO muxi;

--
-- Name: memories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: muxi
--

ALTER SEQUENCE public.memories_id_seq OWNED BY public.memories.id;


--
-- Name: scheduled_job_audit; Type: TABLE; Schema: public; Owner: muxi
--

CREATE TABLE public.scheduled_job_audit (
    id integer NOT NULL,
    job_id character varying(255) NOT NULL,
    user_id character varying(255) NOT NULL,
    action character varying(50) NOT NULL,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    changes text,
    reason text,
    CONSTRAINT chk_audit_action CHECK (((action)::text = ANY ((ARRAY['created'::character varying, 'updated'::character varying, 'paused'::character varying, 'resumed'::character varying, 'deleted'::character varying, 'replaced'::character varying])::text[])))
);


ALTER TABLE public.scheduled_job_audit OWNER TO muxi;

--
-- Name: TABLE scheduled_job_audit; Type: COMMENT; Schema: public; Owner: muxi
--

COMMENT ON TABLE public.scheduled_job_audit IS 'Audit trail for scheduled job lifecycle events. Does not track executions.';


--
-- Name: scheduled_job_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: muxi
--

CREATE SEQUENCE public.scheduled_job_audit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduled_job_audit_id_seq OWNER TO muxi;

--
-- Name: scheduled_job_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: muxi
--

ALTER SEQUENCE public.scheduled_job_audit_id_seq OWNED BY public.scheduled_job_audit.id;


--
-- Name: scheduled_jobs; Type: TABLE; Schema: public; Owner: muxi
--

CREATE TABLE public.scheduled_jobs (
    id character varying(255) DEFAULT concat('sched_', public.nanoid()) NOT NULL,
    user_id character varying(255) NOT NULL,
    formation_id character varying(255) NOT NULL,
    title character varying(500) NOT NULL,
    original_prompt text NOT NULL,
    execution_prompt text NOT NULL,
    cron_expression character varying(255),
    exclusion_rules jsonb DEFAULT '[]'::jsonb,
    status character varying(20) DEFAULT 'ACTIVE'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    last_run_at timestamp with time zone,
    last_run_status character varying(20),
    last_run_failure_message text,
    total_runs integer DEFAULT 0,
    total_failures integer DEFAULT 0,
    consecutive_failures integer DEFAULT 0,
    metadata jsonb DEFAULT '{}'::jsonb,
    is_recurring boolean DEFAULT true NOT NULL,
    scheduled_for timestamp with time zone,
    job_metadata text DEFAULT '{}'::text,
    CONSTRAINT scheduled_jobs_consecutive_failures_check CHECK ((consecutive_failures >= 0)),
    CONSTRAINT scheduled_jobs_last_run_status_check CHECK (((last_run_status IS NULL) OR ((last_run_status)::text = ANY ((ARRAY['success'::character varying, 'failed'::character varying])::text[])))),
    CONSTRAINT scheduled_jobs_scheduling_check CHECK ((((is_recurring = true) AND (cron_expression IS NOT NULL) AND (scheduled_for IS NULL)) OR ((is_recurring = false) AND (cron_expression IS NULL) AND (scheduled_for IS NOT NULL)))),
    CONSTRAINT scheduled_jobs_status_check CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'PAUSED'::character varying, 'COMPLETED'::character varying])::text[]))),
    CONSTRAINT scheduled_jobs_total_failures_check CHECK ((total_failures >= 0)),
    CONSTRAINT scheduled_jobs_total_runs_check CHECK ((total_runs >= 0))
);


ALTER TABLE public.scheduled_jobs OWNER TO muxi;

--
-- Name: users; Type: TABLE; Schema: public; Owner: muxi
--

CREATE TABLE public.users (
    id integer NOT NULL,
    public_id character(21) NOT NULL,
    external_user_id text NOT NULL,
    external_user_id_hash character varying(64) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.users OWNER TO muxi;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: muxi
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO muxi;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: muxi
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: collections id; Type: DEFAULT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.collections ALTER COLUMN id SET DEFAULT nextval('public.collections_id_seq'::regclass);


--
-- Name: credentials id; Type: DEFAULT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.credentials ALTER COLUMN id SET DEFAULT nextval('public.credentials_id_seq'::regclass);


--
-- Name: memories id; Type: DEFAULT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.memories ALTER COLUMN id SET DEFAULT nextval('public.memories_id_seq'::regclass);


--
-- Name: scheduled_job_audit id; Type: DEFAULT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.scheduled_job_audit ALTER COLUMN id SET DEFAULT nextval('public.scheduled_job_audit_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: collections collections_collection_id_key; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.collections
    ADD CONSTRAINT collections_collection_id_key UNIQUE (collection_id);


--
-- Name: collections collections_pkey; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.collections
    ADD CONSTRAINT collections_pkey PRIMARY KEY (id);


--
-- Name: credentials credentials_credential_id_key; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_credential_id_key UNIQUE (credential_id);


--
-- Name: credentials credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_pkey PRIMARY KEY (id);


--
-- Name: memories memories_memory_id_key; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_memory_id_key UNIQUE (memory_id);


--
-- Name: memories memories_pkey; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_pkey PRIMARY KEY (id);


--
-- Name: scheduled_job_audit scheduled_job_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.scheduled_job_audit
    ADD CONSTRAINT scheduled_job_audit_pkey PRIMARY KEY (id);


--
-- Name: scheduled_jobs scheduled_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.scheduled_jobs
    ADD CONSTRAINT scheduled_jobs_pkey PRIMARY KEY (id);


--
-- Name: users uq_users_external_id_hash; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_external_id_hash UNIQUE (external_user_id_hash);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_user_id_key; Type: CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_user_id_key UNIQUE (public_id);


--
-- Name: idx_collections_collection_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_collections_collection_id ON public.collections USING btree (collection_id);


--
-- Name: idx_collections_created_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_collections_created_at ON public.collections USING btree (created_at);


--
-- Name: idx_collections_name; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_collections_name ON public.collections USING btree (name);


--
-- Name: idx_collections_updated_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_collections_updated_at ON public.collections USING btree (updated_at);


--
-- Name: idx_collections_user_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_collections_user_id ON public.collections USING btree (user_id);


--
-- Name: idx_credentials_created_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_credentials_created_at ON public.credentials USING btree (created_at);


--
-- Name: idx_credentials_credential_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_credentials_credential_id ON public.credentials USING btree (credential_id);


--
-- Name: idx_credentials_service; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_credentials_service ON public.credentials USING btree (service);


--
-- Name: idx_credentials_updated_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_credentials_updated_at ON public.credentials USING btree (updated_at);


--
-- Name: idx_credentials_user_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_credentials_user_id ON public.credentials USING btree (user_id);


--
-- Name: idx_job_audit_job_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_job_audit_job_id ON public.scheduled_job_audit USING btree (job_id);


--
-- Name: idx_job_audit_timestamp; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_job_audit_timestamp ON public.scheduled_job_audit USING btree ("timestamp" DESC);


--
-- Name: idx_job_audit_user_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_job_audit_user_id ON public.scheduled_job_audit USING btree (user_id);


--
-- Name: idx_memories_collection_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_collection_id ON public.memories USING btree (collection_id);


--
-- Name: idx_memories_created_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_created_at ON public.memories USING btree (created_at);


--
-- Name: idx_memories_memory_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_memory_id ON public.memories USING btree (memory_id);


--
-- Name: idx_memories_source; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_source ON public.memories USING btree (source);


--
-- Name: idx_memories_type; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_type ON public.memories USING btree (type);


--
-- Name: idx_memories_updated_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_updated_at ON public.memories USING btree (updated_at);


--
-- Name: idx_memories_user_created_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_user_created_at ON public.memories USING btree (user_id, created_at);


--
-- Name: idx_memories_user_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_memories_user_id ON public.memories USING btree (user_id);


--
-- Name: idx_scheduled_jobs_active_jobs; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_active_jobs ON public.scheduled_jobs USING btree (status, cron_expression) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: idx_scheduled_jobs_cron_expression; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_cron_expression ON public.scheduled_jobs USING btree (cron_expression);


--
-- Name: idx_scheduled_jobs_formation_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_formation_id ON public.scheduled_jobs USING btree (formation_id);


--
-- Name: idx_scheduled_jobs_is_recurring; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_is_recurring ON public.scheduled_jobs USING btree (is_recurring);


--
-- Name: idx_scheduled_jobs_job_metadata; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_job_metadata ON public.scheduled_jobs USING gin (((job_metadata)::jsonb));


--
-- Name: idx_scheduled_jobs_last_run_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_last_run_at ON public.scheduled_jobs USING btree (last_run_at);


--
-- Name: idx_scheduled_jobs_onetime_due; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_onetime_due ON public.scheduled_jobs USING btree (is_recurring, scheduled_for, status) WHERE (is_recurring = false);


--
-- Name: idx_scheduled_jobs_recurring_active; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_recurring_active ON public.scheduled_jobs USING btree (is_recurring, status, cron_expression) WHERE ((is_recurring = true) AND ((status)::text = 'ACTIVE'::text));


--
-- Name: idx_scheduled_jobs_scheduled_for; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_scheduled_for ON public.scheduled_jobs USING btree (scheduled_for);


--
-- Name: idx_scheduled_jobs_status; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_status ON public.scheduled_jobs USING btree (status);


--
-- Name: idx_scheduled_jobs_type_status; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_type_status ON public.scheduled_jobs USING btree (is_recurring, status);


--
-- Name: idx_scheduled_jobs_user_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_user_id ON public.scheduled_jobs USING btree (user_id);


--
-- Name: idx_scheduled_jobs_user_status; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_scheduled_jobs_user_status ON public.scheduled_jobs USING btree (user_id, status);


--
-- Name: idx_users_created_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_users_created_at ON public.users USING btree (created_at);


--
-- Name: idx_users_external_user_id_hash; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_users_external_user_id_hash ON public.users USING btree (external_user_id_hash);


--
-- Name: idx_users_updated_at; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_users_updated_at ON public.users USING btree (updated_at);


--
-- Name: idx_users_user_id; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX idx_users_user_id ON public.users USING btree (public_id);


--
-- Name: memories_embedding_idx; Type: INDEX; Schema: public; Owner: muxi
--

CREATE INDEX memories_embedding_idx ON public.memories USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: scheduled_jobs trigger_update_scheduled_jobs_updated_at; Type: TRIGGER; Schema: public; Owner: muxi
--

CREATE TRIGGER trigger_update_scheduled_jobs_updated_at BEFORE UPDATE ON public.scheduled_jobs FOR EACH ROW EXECUTE FUNCTION public.update_scheduled_jobs_updated_at();


--
-- Name: collections collections_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.collections
    ADD CONSTRAINT collections_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: credentials credentials_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: memories memories_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.collections(id) ON DELETE SET NULL;


--
-- Name: memories memories_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: muxi
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT ALL ON SCHEMA public TO muxi;


--
-- PostgreSQL database dump complete
--

\unrestrict GDgFhqigmUtcU56my9PhadjkDTQG5GRvey6hV42eCvvU3XtYJOMVvPLeDwPpCRr

