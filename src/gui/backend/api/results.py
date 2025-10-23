"""Results browsing and export endpoints."""
import csv
import json
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..services.job_manager import JobManager
from ..schemas.job import JobDetail

router = APIRouter(prefix="/api/results", tags=["results"])
job_manager = JobManager()


@router.get("/{job_id}/papers")
async def get_papers(
    job_id: str,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get papers from a completed job."""
    job = job_manager.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get the output directory from job
    if not job.output_directory:
        raise HTTPException(status_code=404, detail="No output directory for this job")

    # Read the aggregated CSV file
    output_path = Path(job.output_directory)
    csv_file = output_path / "aggregated_data.csv"

    if not csv_file.exists():
        raise HTTPException(status_code=404, detail="Results file not found")

    try:
        papers = []
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                row_num = 0
                for row in reader:
                    # Apply search filter if provided
                    if search:
                        search_lower = search.lower()
                        if not any(
                            search_lower in str(v).lower()
                            for v in row.values()
                        ):
                            continue

                    row_num += 1
                    if row_num > offset and row_num <= offset + limit:
                        papers.append(row)

        # Count total papers matching search
        total = 0
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if search:
                    search_lower = search.lower()
                    if any(search_lower in str(v).lower() for v in row.values()):
                        total += 1
                else:
                    total += 1

        return {
            "papers": papers,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read papers: {str(e)}")


@router.get("/{job_id}/export")
async def export_results(
    job_id: str,
    format: str = "csv",
    db: Session = Depends(get_db),
):
    """Export results in various formats."""
    job = job_manager.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.output_directory:
        raise HTTPException(status_code=404, detail="No output directory for this job")

    output_path = Path(job.output_directory)
    csv_file = output_path / "aggregated_data.csv"

    if not csv_file.exists():
        raise HTTPException(status_code=404, detail="Results file not found")

    try:
        if format == "csv":
            # Return the CSV file directly
            return FileResponse(
                csv_file,
                media_type="text/csv",
                filename=f"{job.name}_results.csv",
            )

        elif format == "json":
            # Convert CSV to JSON
            papers = []
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                papers = list(reader)

            # Create JSON response
            json_data = {
                "job_id": job_id,
                "job_name": job.name,
                "created_at": job.created_at.isoformat(),
                "papers_found": job.papers_found,
                "papers": papers,
            }

            # Create temporary JSON file and return it
            json_file = output_path / f"{job.name}_results.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            return FileResponse(
                json_file,
                media_type="application/json",
                filename=f"{job.name}_results.json",
            )

        elif format == "bibtex":
            # Convert CSV to BibTeX
            papers = []
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                papers = list(reader)

            bibtex_content = "% BibTeX export from SciLEx\n\n"
            for i, paper in enumerate(papers, 1):
                title = paper.get("title", f"Paper {i}")
                authors = paper.get("authors", "Unknown")
                year = paper.get("year", "")
                doi = paper.get("DOI", "")
                venue = paper.get("venue", "")

                bibtex_entry = f"@article{{paper{i},\n"
                bibtex_entry += f'  title = "{{{title}}},\n'
                bibtex_entry += f'  author = {{{authors}}},\n'
                if year:
                    bibtex_entry += f'  year = {{{year}}},\n'
                if venue:
                    bibtex_entry += f'  journal = {{{venue}}},\n'
                if doi:
                    bibtex_entry += f'  doi = {{{doi}}},\n'
                bibtex_entry += "}\n\n"

                bibtex_content += bibtex_entry

            # Create BibTeX file and return it
            bib_file = output_path / f"{job.name}_results.bib"
            with open(bib_file, "w", encoding="utf-8") as f:
                f.write(bibtex_content)

            return FileResponse(
                bib_file,
                media_type="application/x-bibtex",
                filename=f"{job.name}_results.bib",
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export results: {str(e)}")


@router.get("/{job_id}/statistics")
async def get_statistics(
    job_id: str,
    db: Session = Depends(get_db),
):
    """Get statistics about a job's results."""
    job = job_manager.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.output_directory:
        return {
            "job_id": job_id,
            "papers_found": 0,
            "duplicates_removed": 0,
            "citations_fetched": 0,
            "average_year": None,
            "doc_types": {},
        }

    output_path = Path(job.output_directory)
    csv_file = output_path / "aggregated_data.csv"

    if not csv_file.exists():
        raise HTTPException(status_code=404, detail="Results file not found")

    try:
        papers = []
        doc_types = {}
        years = []

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                papers.append(row)

                # Count document types
                doc_type = row.get("type", "Unknown")
                doc_types[doc_type] = doc_types.get(doc_type, 0) + 1

                # Collect years
                year_str = row.get("year", "")
                if year_str and year_str.isdigit():
                    years.append(int(year_str))

        # Calculate average year
        average_year = sum(years) / len(years) if years else None

        return {
            "job_id": job_id,
            "papers_found": len(papers),
            "duplicates_removed": job.duplicates_removed or 0,
            "citations_fetched": job.citations_fetched or 0,
            "average_year": round(average_year, 1) if average_year else None,
            "doc_types": doc_types,
            "earliest_year": min(years) if years else None,
            "latest_year": max(years) if years else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute statistics: {str(e)}")
