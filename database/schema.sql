--
-- PostgreSQL database dump
--

\restrict 9X0IVxcnyyiPyWSxVGDsMmILlz7IZYUuq5hqphXeGv1Ld7OFntVcbE3BitMipJ6



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
-- Name: call_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.call_status AS ENUM (
    'PENDING',
    'PROCESSING',
    'COMPLETED',
    'FAILED'
);


ALTER TYPE public.call_status OWNER TO postgres;

--
-- Name: employee_role; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.employee_role AS ENUM (
    'AGENT',
    'QA',
    'BOTH'
);


ALTER TYPE public.employee_role OWNER TO postgres;

--
-- Name: severity_level; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.severity_level AS ENUM (
    'Minor',
    'Moderate',
    'Major',
    'Critical'
);


ALTER TYPE public.severity_level OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: calls; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.calls (
    call_id uuid DEFAULT gen_random_uuid() NOT NULL,
    customer_id uuid,
    employee_id uuid NOT NULL,
    drive_file_id text NOT NULL,
    drive_folder_id text,
    original_filename text NOT NULL,
    duration_seconds numeric(10,3),
    size_bytes bigint,
    sample_rate_hz integer,
    channels integer,
    sha256 text,
    status public.call_status DEFAULT 'PENDING'::public.call_status NOT NULL,
    current_step text,
    error_message text,
    call_time timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.calls OWNER TO postgres;

--
-- Name: customers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customers (
    customer_id uuid DEFAULT gen_random_uuid() NOT NULL,
    external_customer_ref text,
    display_name text,
    phone_hash text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.customers OWNER TO postgres;

--
-- Name: employees; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.employees (
    employee_id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_code text,
    full_name text NOT NULL,
    role public.employee_role NOT NULL,
    assigned_qa_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_agent_has_qa CHECK ((((role = ANY (ARRAY['AGENT'::public.employee_role, 'BOTH'::public.employee_role])) AND (assigned_qa_id IS NOT NULL)) OR (role = 'QA'::public.employee_role)))
);


ALTER TABLE public.employees OWNER TO postgres;

--
-- Name: qa_reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.qa_reports (
    report_id uuid DEFAULT gen_random_uuid() NOT NULL,
    call_id uuid NOT NULL,
    qa_id uuid NOT NULL,
    overall_score numeric(5,2) NOT NULL,
    grade text GENERATED ALWAYS AS (
CASE
    WHEN (overall_score >= (95)::numeric) THEN 'A+'::text
    WHEN (overall_score >= (90)::numeric) THEN 'A'::text
    WHEN (overall_score >= (86)::numeric) THEN 'A-'::text
    WHEN (overall_score >= (82)::numeric) THEN 'B+'::text
    WHEN (overall_score >= (78)::numeric) THEN 'B'::text
    WHEN (overall_score >= (74)::numeric) THEN 'B-'::text
    WHEN (overall_score >= (70)::numeric) THEN 'C+'::text
    WHEN (overall_score >= (66)::numeric) THEN 'C'::text
    WHEN (overall_score >= (60)::numeric) THEN 'C-'::text
    ELSE 'F'::text
END) STORED,
    severity public.severity_level NOT NULL,
    dimension_scores jsonb NOT NULL,
    dimension_reports jsonb,
    evidence jsonb,
    confidence_scores jsonb,
    report_json jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT qa_reports_overall_score_check CHECK (((overall_score >= (0)::numeric) AND (overall_score <= (100)::numeric)))
);


ALTER TABLE public.qa_reports OWNER TO postgres;

--
-- Name: transcripts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transcripts (
    transcript_id uuid DEFAULT gen_random_uuid() NOT NULL,
    call_id uuid NOT NULL,
    full_text text NOT NULL,
    speaker_turns jsonb,
    asr_engine text,
    asr_model text,
    avg_confidence numeric(5,4),
    wer numeric(6,5),
    diarization_engine text,
    der numeric(6,5),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.transcripts OWNER TO postgres;

--
-- Name: calls calls_drive_file_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_drive_file_id_key UNIQUE (drive_file_id);


--
-- Name: calls calls_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_pkey PRIMARY KEY (call_id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (customer_id);


--
-- Name: employees employees_employee_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_employee_code_key UNIQUE (employee_code);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (employee_id);


--
-- Name: qa_reports qa_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.qa_reports
    ADD CONSTRAINT qa_reports_pkey PRIMARY KEY (report_id);


--
-- Name: transcripts transcripts_call_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transcripts
    ADD CONSTRAINT transcripts_call_id_key UNIQUE (call_id);


--
-- Name: transcripts transcripts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transcripts
    ADD CONSTRAINT transcripts_pkey PRIMARY KEY (transcript_id);


--
-- Name: idx_calls_customer_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_calls_customer_created ON public.calls USING btree (customer_id, created_at DESC);


--
-- Name: idx_calls_employee_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_calls_employee_created ON public.calls USING btree (employee_id, created_at DESC);


--
-- Name: idx_calls_status_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_calls_status_created ON public.calls USING btree (status, created_at DESC);


--
-- Name: idx_reports_call_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reports_call_created ON public.qa_reports USING btree (call_id, created_at DESC);


--
-- Name: idx_reports_grade; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reports_grade ON public.qa_reports USING btree (grade);


--
-- Name: idx_reports_qa_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reports_qa_created ON public.qa_reports USING btree (qa_id, created_at DESC);


--
-- Name: idx_reports_severity; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reports_severity ON public.qa_reports USING btree (severity);


--
-- Name: employees fk_assigned_qa; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT fk_assigned_qa FOREIGN KEY (assigned_qa_id) REFERENCES public.employees(employee_id) ON DELETE SET NULL;


--
-- Name: calls fk_calls_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT fk_calls_customer FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id) ON DELETE SET NULL;


--
-- Name: calls fk_calls_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT fk_calls_employee FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: qa_reports fk_reports_call; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.qa_reports
    ADD CONSTRAINT fk_reports_call FOREIGN KEY (call_id) REFERENCES public.calls(call_id) ON DELETE CASCADE;


--
-- Name: qa_reports fk_reports_qa; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.qa_reports
    ADD CONSTRAINT fk_reports_qa FOREIGN KEY (qa_id) REFERENCES public.employees(employee_id) ON DELETE RESTRICT;


--
-- Name: transcripts fk_transcripts_call; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transcripts
    ADD CONSTRAINT fk_transcripts_call FOREIGN KEY (call_id) REFERENCES public.calls(call_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict 9X0IVxcnyyiPyWSxVGDsMmILlz7IZYUuq5hqphXeGv1Ld7OFntVcbE3BitMipJ6

