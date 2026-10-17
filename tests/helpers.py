def make_pdf(path, lines):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    try:
        pdfmetrics.getFont("STSong-Light")
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(path))
    c.setFont("STSong-Light", 11)
    y = 800
    for line in lines:
        if line == "<PAGE>":
            c.showPage()
            c.setFont("STSong-Light", 11)
            y = 800
            continue
        c.drawString(40, y, line)
        y -= 18
    c.save()
    return path


def add_disclosure(company, title, ann_date, local_path=None, ann_id=None):
    from ashare.models import SessionLocal, Disclosure
    from ashare.disclosures import classify_title
    s = SessionLocal()
    try:
        d = Disclosure(company_id=company.id, announcement_id=ann_id or title, announcement_date=ann_date,
                       title_cn=title, kind=classify_title(title), local_path=str(local_path) if local_path else None,
                       source="CNINFO", document_url=f"https://static.cninfo.com.cn/{ann_id or 'x'}.PDF")
        s.add(d)
        s.commit()
        return d
    finally:
        s.close()
