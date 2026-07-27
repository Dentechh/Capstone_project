from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Service:
    id: str
    title: str
    short_desc: str
    full_desc: str
    benefits: List[str] = field(default_factory=list)
    image: str = ""

    @classmethod
    def get_services_data(cls) -> dict:
        return {
            "cleaning": cls(
                id="cleaning",
                title="Oral Prophylaxis (Cleaning)",
                short_desc="Keep your gums healthy and your smile bright.",
                full_desc="Oral prophylaxis is a thorough dental cleaning procedure performed by our professionals. It involves the removal of dental plaque and tartar to prevent cavities, gingivitis, and gum disease.",
                benefits=[
                    "Prevents tooth decay and gum disease",
                    "Removes stubborn stains for a whiter smile",
                    "Eliminates bad breath",
                    "Early detection of dental issues",
                ],
                image="cleaning.jpg",
            ),
            "root-canal": cls(
                id="root-canal",
                title="Root Canal Treatment",
                short_desc="Save your natural tooth and relieve severe pain.",
                full_desc="A root canal is a treatment to repair and save a badly damaged or infected tooth instead of removing it. The procedure involves removing the damaged area of the tooth (the pulp) and cleaning and disinfecting it.",
                benefits=[
                    "Stops the spread of infection",
                    "Relieves severe toothache",
                    "Preserves your natural tooth structure",
                    "Highly successful and long-lasting",
                ],
                image="root-canal.jpg",
            ),
            "consultation": cls(
                id="consultation",
                title="Dental Consultation",
                short_desc="Start your journey to a healthier smile with a professional check-up.",
                full_desc="A comprehensive dental examination where our dentists assess your overall oral health. This includes checking for cavities, gum disease, and oral cancer, followed by a personalized treatment plan.",
                benefits=[
                    "Comprehensive oral health assessment",
                    "Personalized treatment planning",
                    "Professional advice on oral hygiene",
                    "Early detection of potential dental problems",
                ],
                image="consultation.jpg",
            ),
            "pasta": cls(
                id="pasta",
                title="Tooth Restoration (Pasta)",
                short_desc="Restore the strength and beauty of your teeth.",
                full_desc="Commonly known as 'Pasta,' this procedure uses tooth-colored composite resins to fill cavities or repair chipped teeth, restoring their natural function and appearance.",
                benefits=[
                    "Matches your natural tooth color",
                    "Prevents further tooth decay",
                    "Restores tooth strength and function",
                    "Quick and minimally invasive procedure",
                ],
                image="pasta.jpg",
            ),
            "extraction": cls(
                id="extraction",
                title="Tooth Extraction",
                short_desc="Safe and gentle removal of problematic teeth.",
                full_desc="When a tooth is too damaged to be saved by a filling or crown, a professional extraction is performed. We ensure the process is as comfortable and pain-free as possible.",
                benefits=[
                    "Eliminates severe dental pain",
                    "Prevents the spread of infection to other teeth",
                    "Prepares for orthodontic or denture treatment",
                    "Fast relief from overcrowded teeth",
                ],
                image="extraction.jpg",
            ),
            "dentures": cls(
                id="dentures",
                title="Dentures",
                short_desc="Regain your smile and confidence with custom-fit dentures.",
                full_desc="Custom-made removable replacements for missing teeth and surrounding tissues. We offer both full and partial dentures designed to look natural and fit comfortably.",
                benefits=[
                    "Restores ability to chew and speak clearly",
                    "Supports facial muscles for a younger look",
                    "Customized for a natural appearance",
                    "Cost-effective solution for missing teeth",
                ],
                image="dentures.jpg",
            ),
            "crowns-bridges": cls(
                id="crowns-bridges",
                title="Crowns and Bridges",
                short_desc="Permanent solutions for broken or missing teeth.",
                full_desc="Dental crowns cover a damaged tooth to restore its shape, while bridges fill the gap created by one or more missing teeth, anchored by healthy teeth on either side.",
                benefits=[
                    "Long-lasting and durable restoration",
                    "Restores the natural shape and size of teeth",
                    "Prevents remaining teeth from shifting",
                    "Enhances overall smile aesthetics",
                ],
                image="crowns-bridges.jpg",
            ),
            "whitening": cls(
                id="whitening",
                title="Teeth Whitening",
                short_desc="Brighten your smile by several shades in one visit.",
                full_desc="A professional cosmetic procedure that uses high-quality whitening agents to remove deep-seated stains caused by coffee, tea, or aging, giving you a radiant smile.",
                benefits=[
                    "Immediate and noticeable results",
                    "Safe and professionally supervised",
                    "Boosts self-confidence",
                    "Removes tough stains that toothpaste can't",
                ],
                image="whitening.jpg",
            ),
            "fluoride": cls(
                id="fluoride",
                title="Fluoride Treatment",
                short_desc="Strengthen your tooth enamel against decay.",
                full_desc="A quick preventive treatment where a high concentration of fluoride is applied to the teeth. This mineral helps rebuild weakened tooth enamel and reverses early signs of cavities.",
                benefits=[
                    "Significantly reduces risk of cavities",
                    "Strengthens tooth enamel",
                    "Especially effective for children's developing teeth",
                    "Protects teeth from acid and bacteria",
                ],
                image="fluoride.jpg",
            ),
            "sealant": cls(
                id="sealant",
                title="Pit and Fissure Sealant",
                short_desc="An invisible shield for your molars.",
                full_desc="A thin, protective coating applied to the chewing surfaces of the back teeth (molars). It seals the deep grooves where food and bacteria often get trapped.",
                benefits=[
                    "Highly effective at preventing molar cavities",
                    "Painless and non-invasive application",
                    "Long-lasting protection for many years",
                    "Ideal for children and teenagers",
                ],
                image="sealant.jpg",
            ),
            "wisdom-tooth": cls(
                id="wisdom-tooth",
                title="Wisdom Teeth Removal",
                short_desc="Prevent pain and crowding caused by impacted wisdom teeth.",
                full_desc="A surgical procedure to remove one or more wisdom teeth—the four permanent adult teeth located at the back corners of your mouth—that don't have enough room to grow.",
                benefits=[
                    "Prevents overcrowding and shifting of teeth",
                    "Relieves jaw pain and gum swelling",
                    "Reduces risk of infection and cysts",
                    "Protects adjacent healthy molars",
                ],
                image="wisdom-tooth.jpg",
            ),
            "xray": cls(
                id="xray",
                title="Periapical X-ray",
                short_desc="Detailed imaging to see what's happening beneath the surface.",
                full_desc="A focused X-ray that shows the entire tooth, from the crown to the end of the root where it anchors into the jaw. Essential for detecting abscesses and deep-seated issues.",
                benefits=[
                    "Accurate diagnosis of root-level problems",
                    "Detects infections and cysts early",
                    "Shows the exact position of impacted teeth",
                    "Critical for successful root canal planning",
                ],
                image="xray.jpg",
            ),
        }

    @classmethod
    def get_by_id(cls, service_id: str) -> Optional["Service"]:
        return cls.get_services_data().get(service_id)

    @property
    def template_context(self) -> dict:
        return {
            "service": self,
        }
